"""Product evidence: upload, extraction and requirement matching.

The distinction this module exists to preserve:

    a document exists  !=  a requirement is satisfied

A temperature-rise test report being on file means the manufacturer has
*something* to show an assessor. It does not mean the appliance passed. The
platform therefore reports ``SUPPORTED`` as "supporting information is on
file", and surfaces any extracted result separately, clearly labelled as read
from the document rather than judged.

Uploaded evidence is kept in its own vector collection. Mixing a manufacturer's
datasheet into the standards index would let a product's own marketing copy be
retrieved and cited as if it were a clause of an Indian Standard.
"""
from __future__ import annotations

import hashlib
import logging
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.constants import UploadCategory
from app.models import ComplianceRequirement, Product, ProductEvidence

logger = logging.getLogger(__name__)

#: Only these are accepted. Anything executable or archive-shaped is refused.
ALLOWED_CONTENT_TYPES = {
    "application/pdf": ".pdf",
    "text/plain": ".txt",
    "image/png": ".png",
    "image/jpeg": ".jpg",
}
ALLOWED_EXTENSIONS = {".pdf", ".txt", ".png", ".jpg", ".jpeg"}

#: Magic bytes, checked because a content-type header is caller-supplied.
MAGIC = {
    b"%PDF": ".pdf",
    b"\x89PNG": ".png",
    b"\xff\xd8\xff": ".jpg",
}

#: Category -> the evidence_type a requirement would ask for.
CATEGORY_TO_EVIDENCE_TYPE = {
    UploadCategory.DATASHEET.value: "document",
    UploadCategory.TEST_REPORT.value: "test_report",
    UploadCategory.PRODUCT_LABEL.value: "marking_artwork",
    UploadCategory.TECHNICAL_DOCUMENT.value: "document",
    UploadCategory.CERTIFICATE.value: "material_certificate",
    UploadCategory.OTHER.value: "document",
}


class EvidenceUploadError(ValueError):
    """Raised for a file the platform will not accept."""


@dataclass
class ExtractedFields:
    """What could be read out of an uploaded document.

    Everything here is *read*, never *judged*. ``result`` records the wording
    found in the document; it is not the platform's conclusion.
    """

    model: Optional[str] = None
    test_names: List[str] = field(default_factory=list)
    result: Optional[str] = None
    ratings: Dict[str, float] = field(default_factory=dict)
    numeric_results: List[Dict[str, Any]] = field(default_factory=list)
    laboratory: Optional[str] = None
    report_number: Optional[str] = None
    issued_on: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "model": self.model,
            "test_names": self.test_names,
            "result": self.result,
            "ratings": self.ratings,
            "numeric_results": self.numeric_results,
            "laboratory": self.laboratory,
            "report_number": self.report_number,
            "issued_on": self.issued_on,
        }


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

def extract_text(path: Path, content_type: str) -> Tuple[str, str]:
    """Return (text, status). Status explains an empty result honestly."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        try:
            import fitz

            with fitz.open(path) as doc:
                text = "\n".join(page.get_text("text") for page in doc)
            if text.strip():
                return text, "extracted"
            return "", "pdf_has_no_text_layer"
        except Exception as exc:  # pragma: no cover - depends on the file
            logger.warning("PDF text extraction failed for %s: %s", path.name, exc)
            return "", "extraction_failed"
    if suffix in (".txt",):
        return path.read_text(encoding="utf-8", errors="ignore"), "extracted"
    if suffix in (".png", ".jpg", ".jpeg"):
        # Images need OCR; that is handled by the OCR service, not here.
        return "", "image_requires_ocr"
    del content_type
    return "", "unsupported"


# ---------------------------------------------------------------------------
# Structured field extraction (deterministic)
# ---------------------------------------------------------------------------

_RESULT_RE = re.compile(r"\b(pass(?:ed)?|fail(?:ed)?|conform(?:s|ed)?|complies)\b", re.I)
_MODEL_RE = re.compile(r"\b(?:model|type|cat\.?\s*no\.?)\s*[:\-]?\s*([A-Za-z0-9][\w\-/.]{1,30})", re.I)
_REPORT_RE = re.compile(r"\b(?:report|certificate)\s*(?:no\.?|number)\s*[:\-]?\s*([\w\-/]{3,32})", re.I)
# Stops at the end of the line: a laboratory name does not run into the next field.
_LAB_RE = re.compile(
    r"\b(?:laborator(?:y|ies)|tested (?:at|by))\s*[:\-]?\s*([A-Za-z][^\r\n]{3,60})", re.I
)
_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b")

_RATING_PATTERNS = [
    ("voltage_v", re.compile(r"(\d+(?:\.\d+)?)\s*(?:v|volts?)\b", re.I)),
    ("power_w", re.compile(r"(\d+(?:\.\d+)?)\s*(?:w|watts?)\b", re.I)),
    ("capacity_litres", re.compile(r"(\d+(?:\.\d+)?)\s*(?:l|litres?|liters?)\b", re.I)),
    ("mass_kg", re.compile(r"(\d+(?:\.\d+)?)\s*(?:kg)\b", re.I)),
]

#: Test names the corpus knows about, so extraction stays inside a closed set
#: rather than inventing a test from arbitrary prose.
KNOWN_TEST_TERMS = [
    "temperature rise", "insulation resistance", "electric strength", "earth continuity",
    "standing loss", "hydrostatic", "burst", "impact absorption", "penetration",
    "retention system", "roll-off", "field of vision", "small parts", "sharp edge",
    "sharp point", "drop test", "torque", "tension", "compression", "migration",
    "abnormal operation", "mechanical strength", "cord anchorage", "gasket endurance",
    "handle load", "marking durability", "humidity",
]

_MEASUREMENT_RE = re.compile(
    r"([A-Za-z][A-Za-z \-/]{2,40}?)\s*[:=]\s*(\d+(?:\.\d+)?)\s*([a-zA-Z°%]{1,10})"
)


def extract_fields(text: str) -> ExtractedFields:
    """Pull structured values out of an uploaded document.

    Deterministic on purpose: these values feed an evidence decision, so they
    must be reproducible and traceable to literal text in the file.
    """
    fields = ExtractedFields()
    if not text or not text.strip():
        return fields

    lowered = text.lower()

    match = _MODEL_RE.search(text)
    if match:
        fields.model = match.group(1).strip()

    match = _REPORT_RE.search(text)
    if match:
        fields.report_number = match.group(1).strip()

    match = _LAB_RE.search(text)
    if match:
        fields.laboratory = re.sub(r"\s+", " ", match.group(1)).strip(" .,-")

    match = _DATE_RE.search(text)
    if match:
        fields.issued_on = match.group(1)

    result = _RESULT_RE.search(text)
    if result:
        # The wording found in the document, not a verdict of ours.
        fields.result = result.group(1).lower()

    fields.test_names = [term for term in KNOWN_TEST_TERMS if term in lowered]

    for key, pattern in _RATING_PATTERNS:
        found = pattern.search(text)
        if found:
            try:
                fields.ratings[key] = float(found.group(1))
            except ValueError:
                continue

    for measurement in _MEASUREMENT_RE.finditer(text):
        label = re.sub(r"\s+", " ", measurement.group(1)).strip().lower()
        if len(fields.numeric_results) >= 12:
            break
        try:
            value = float(measurement.group(2))
        except ValueError:
            continue
        fields.numeric_results.append(
            {"label": label, "value": value, "unit": measurement.group(3)}
        )

    return fields


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

def _safe_suffix(filename: str, content_type: str, head: bytes) -> str:
    for magic, suffix in MAGIC.items():
        if head.startswith(magic):
            return suffix
    suffix = Path(filename or "").suffix.lower()
    if suffix in ALLOWED_EXTENSIONS:
        return ".jpg" if suffix == ".jpeg" else suffix
    mapped = ALLOWED_CONTENT_TYPES.get((content_type or "").split(";")[0].strip())
    if mapped:
        return mapped
    raise EvidenceUploadError(
        "Only PDF, TXT, PNG and JPEG evidence files are accepted."
    )


class EvidenceService:
    def __init__(self) -> None:
        self.upload_dir = Path(settings.upload_dir)

    # ------------------------------------------------------------------
    def store_upload(
        self,
        db: Session,
        product: Product,
        *,
        filename: str,
        content_type: str,
        data: bytes,
        category: str = UploadCategory.OTHER.value,
        display_name: str = "",
    ) -> ProductEvidence:
        if not data:
            raise EvidenceUploadError("The uploaded file is empty.")

        limit = settings.max_upload_mb * 1024 * 1024
        if len(data) > limit:
            raise EvidenceUploadError(
                f"File is larger than the {settings.max_upload_mb} MB limit."
            )

        try:
            category_value = UploadCategory(category).value
        except ValueError:
            category_value = UploadCategory.OTHER.value

        suffix = _safe_suffix(filename, content_type, data[:8])

        # The stored name is generated, never taken from the upload, so a
        # crafted filename cannot escape the upload directory.
        digest = hashlib.sha256(data).hexdigest()[:16]
        evidence_id = f"ev-{uuid.uuid4().hex[:12]}"
        target_dir = self.upload_dir / product.id
        target_dir.mkdir(parents=True, exist_ok=True)
        stored = target_dir / f"{evidence_id}-{digest}{suffix}"
        stored.write_bytes(data)

        text, status = extract_text(stored, content_type)
        fields = extract_fields(text)

        record = ProductEvidence(
            id=evidence_id,
            product_id=product.id,
            evidence_type=CATEGORY_TO_EVIDENCE_TYPE.get(category_value, "document"),
            name=display_name.strip() or Path(filename).stem or evidence_id,
            value="",
            file_path=str(stored),
            original_filename=Path(filename).name[:255],
            content_type=(content_type or "")[:127],
            size_bytes=len(data),
            upload_category=category_value,
            extracted_text=text[:200_000],
            extracted_fields_json=fields.as_dict(),
            extraction_status=status,
            metadata_json={"sha256_prefix": digest},
        )
        db.add(record)
        db.commit()
        db.refresh(record)

        self._index(record)
        return record

    # ------------------------------------------------------------------
    @staticmethod
    def _index(record: ProductEvidence) -> None:
        """Index into the product-evidence collection, never the standards one."""
        if not (record.extracted_text or "").strip():
            return
        try:
            from app.search.vector_store import PRODUCT_EVIDENCE_COLLECTION, get_vector_store

            get_vector_store().upsert(
                PRODUCT_EVIDENCE_COLLECTION,
                [record.id],
                [f"{record.name}. {record.extracted_text[:4000]}"],
                [
                    {
                        "evidence_id": record.id,
                        "product_id": record.product_id,
                        "evidence_type": record.evidence_type,
                        "upload_category": record.upload_category,
                        "document_type": "product_evidence",
                    }
                ],
            )
        except Exception as exc:  # pragma: no cover - store dependent
            logger.warning("Could not index evidence %s: %s", record.id, exc)

    # ------------------------------------------------------------------
    def delete(self, db: Session, record: ProductEvidence) -> None:
        if record.file_path:
            try:
                Path(record.file_path).unlink(missing_ok=True)
            except OSError as exc:  # pragma: no cover
                logger.warning("Could not remove %s: %s", record.file_path, exc)
        db.delete(record)
        db.commit()


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

@dataclass
class EvidenceAssessment:
    """What an uploaded document says about one requirement."""

    evidence: Optional[ProductEvidence]
    #: A document of the right kind mentioning the right subject was found.
    document_present: bool = False
    #: The document states a result. Read from the file, not judged by us.
    stated_result: Optional[str] = None
    matched_terms: List[str] = field(default_factory=list)
    note: str = ""

    @property
    def satisfied(self) -> bool:
        """Deliberately absent as a concept.

        Kept as a property so that any caller reaching for it gets the point
        rather than a value: presence of a document is never satisfaction of a
        requirement.
        """
        raise NotImplementedError(
            "Evidence presence is not requirement satisfaction. Use "
            "document_present, and let the gap analyzer assign a status."
        )


class EvidenceMatchingService:
    """Match uploaded documents to requirements, without judging them."""

    def assess(
        self, requirement: ComplianceRequirement, evidence: Sequence[ProductEvidence]
    ) -> EvidenceAssessment:
        keywords = [
            k.lower()
            for k in (requirement.check_rule_json or {}).get("match_keywords", [])
            if k
        ]
        from app.compliance.gap_analyzer import EVIDENCE_EQUIVALENTS

        accepted = EVIDENCE_EQUIVALENTS.get(
            requirement.evidence_type, {requirement.evidence_type}
        )

        best: Optional[ProductEvidence] = None
        best_terms: List[str] = []
        for item in evidence:
            if item.evidence_type not in accepted:
                continue
            haystack = " ".join(
                [
                    item.name or "",
                    item.value or "",
                    item.original_filename or "",
                    (item.extracted_text or "")[:20000],
                ]
            ).lower()
            covers = (item.metadata_json or {}).get("covers") or []
            if isinstance(covers, list) and requirement.requirement_code in covers:
                return EvidenceAssessment(
                    evidence=item,
                    document_present=True,
                    stated_result=(item.extracted_fields_json or {}).get("result"),
                    matched_terms=[requirement.requirement_code],
                    note="The document explicitly declares that it covers this requirement.",
                )
            terms = [k for k in keywords if k in haystack]
            if len(terms) > len(best_terms):
                best, best_terms = item, terms

        if best is None or not best_terms:
            return EvidenceAssessment(evidence=None, note="No matching document was supplied.")

        stated = (best.extracted_fields_json or {}).get("result")
        note = (
            f"'{best.name}' is a {best.evidence_type.replace('_', ' ')} mentioning "
            f"{', '.join(best_terms[:3])}."
        )
        if stated:
            note += (
                f" The document states '{stated}' - that wording was read from the file, "
                "not assessed by this platform."
            )
        else:
            note += (
                " The platform records that the document exists; it does not determine "
                "whether the requirement is met."
            )
        return EvidenceAssessment(
            evidence=best,
            document_present=True,
            stated_result=stated,
            matched_terms=best_terms,
            note=note,
        )


_service: Optional[EvidenceService] = None


def get_evidence_service() -> EvidenceService:
    global _service
    if _service is None:
        _service = EvidenceService()
    return _service
