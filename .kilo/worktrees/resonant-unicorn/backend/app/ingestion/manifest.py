"""Source manifest: the provenance record for every document in the corpus.

A PDF has no header block to declare where it came from, so the manifest is
what makes a document *verified*. Ingestion reads it, and the rules below are
enforced at load time rather than trusted:

* A document may only claim ``is_verified: true`` if it carries a
  ``source_url`` and a ``retrieved_at`` date. Provenance without a source is
  not provenance.
* A ``DEMO-STD-*`` identifier can never be marked verified, and an entry
  claiming to be verified can never use a demo identifier. This is the rule
  that stops a synthetic record being presented as a real Indian Standard.
* An entry whose local file is missing is reported, not silently skipped.

Entries are matched to files by ``local_path`` (preferred) or by filename.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.core.constants import DocumentType, SourceType

logger = logging.getLogger(__name__)

MANIFEST_PATH = settings.data_dir / "source_manifest.json"

DEMO_PREFIXES = ("DEMO-", "SAMPLE-", "TEST-")


@dataclass
class ManifestEntry:
    document_id: str
    title: str = ""
    is_number: str = ""
    standard_id: str = ""
    document_type: str = DocumentType.STANDARD.value
    source_url: Optional[str] = None
    source_type: str = SourceType.DEMO.value
    is_verified: bool = False
    is_demo: bool = True
    retrieved_at: Optional[str] = None
    local_path: str = ""
    notes: str = ""
    #: Cataloguing metadata for retrieval routing. A PDF carries no header
    #: block, so without this an official document has no category or keywords
    #: and cannot be matched to a product. These describe *how the document is
    #: filed*, derived from its own title - they are not claims about the
    #: content of the standard.
    product_category: str = ""
    keywords: List[str] = field(default_factory=list)
    covered_areas: List[str] = field(default_factory=list)

    @property
    def filename(self) -> str:
        return Path(self.local_path).name if self.local_path else ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "document_id": self.document_id,
            "title": self.title,
            "is_number": self.is_number,
            "standard_id": self.standard_id,
            "document_type": self.document_type,
            "source_url": self.source_url,
            "source_type": self.source_type,
            "is_verified": self.is_verified,
            "is_demo": self.is_demo,
            "retrieved_at": self.retrieved_at,
            "local_path": self.local_path,
            "notes": self.notes,
            "product_category": self.product_category,
            "keywords": self.keywords,
            "covered_areas": self.covered_areas,
        }


@dataclass
class ManifestReport:
    entries: List[ManifestEntry] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def verified_count(self) -> int:
        return sum(1 for e in self.entries if e.is_verified)

    @property
    def demo_count(self) -> int:
        return sum(1 for e in self.entries if e.is_demo)


def looks_like_demo_identifier(value: str) -> bool:
    return (value or "").strip().upper().startswith(DEMO_PREFIXES)


def validate_entry(raw: Dict[str, Any]) -> tuple:
    """Return (entry, errors). An entry with errors is never marked verified."""
    errors: List[str] = []
    document_id = str(raw.get("document_id") or raw.get("standard_id") or "").strip()
    if not document_id:
        errors.append("entry has no document_id")

    is_verified = bool(raw.get("is_verified", False))
    is_demo = bool(raw.get("is_demo", not is_verified))
    is_number = str(raw.get("is_number") or "").strip()
    standard_id = str(raw.get("standard_id") or document_id).strip()
    source_url = raw.get("source_url") or None
    retrieved_at = raw.get("retrieved_at") or None

    # --- the rules that keep synthetic data out of the verified corpus ---
    if is_verified:
        if not source_url:
            errors.append(
                f"{document_id}: is_verified=true requires a source_url "
                "(provenance without a source is not provenance)"
            )
        if not retrieved_at:
            errors.append(f"{document_id}: is_verified=true requires retrieved_at")
        if looks_like_demo_identifier(is_number) or looks_like_demo_identifier(standard_id):
            errors.append(
                f"{document_id}: a DEMO-* identifier cannot be marked verified - "
                "synthetic records must never be presented as official standards"
            )
        if is_demo:
            errors.append(f"{document_id}: an entry cannot be both is_verified and is_demo")

    if is_demo and not looks_like_demo_identifier(standard_id) and not looks_like_demo_identifier(is_number):
        # Not fatal, but a synthetic record with a real-looking number is exactly
        # the failure mode the manifest exists to prevent.
        errors.append(
            f"{document_id}: is_demo=true but the identifier '{standard_id or is_number}' "
            "does not use a DEMO-* prefix; synthetic records must be unmistakable"
        )

    if errors:
        is_verified = False
        is_demo = True

    entry = ManifestEntry(
        document_id=document_id or "unknown",
        title=str(raw.get("title") or ""),
        is_number=is_number,
        standard_id=standard_id,
        document_type=str(raw.get("document_type") or DocumentType.STANDARD.value),
        source_url=source_url,
        source_type=str(
            raw.get("source_type")
            or (SourceType.OFFICIAL.value if is_verified else SourceType.DEMO.value)
        ),
        is_verified=is_verified,
        is_demo=is_demo,
        retrieved_at=retrieved_at,
        local_path=str(raw.get("local_path") or raw.get("file") or ""),
        notes=str(raw.get("notes") or ""),
        product_category=str(raw.get("product_category") or ""),
        keywords=[str(k).strip().lower() for k in (raw.get("keywords") or []) if str(k).strip()],
        covered_areas=[str(a).strip() for a in (raw.get("covered_areas") or []) if str(a).strip()],
    )
    return entry, errors


def load_manifest(path: Optional[Path] = None) -> ManifestReport:
    path = path or MANIFEST_PATH
    report = ManifestReport()
    if not path.exists():
        report.warnings.append(f"No source manifest at {path}")
        return report

    payload = json.loads(path.read_text(encoding="utf-8"))
    documents = payload.get("documents", [])
    seen: set = set()

    for raw in documents:
        if str(raw.get("standard_id", "")).strip() == "*":
            continue  # aggregate row describing a seed file, not a document
        entry, errors = validate_entry(raw)
        report.errors.extend(errors)
        if entry.document_id in seen:
            report.warnings.append(f"duplicate document_id {entry.document_id}")
        seen.add(entry.document_id)

        if entry.local_path:
            resolved = (settings.data_dir.parent / entry.local_path)
            if not resolved.exists():
                report.warnings.append(
                    f"{entry.document_id}: local file not found at {entry.local_path}"
                )
        report.entries.append(entry)

    for error in report.errors:
        logger.error("Manifest validation: %s", error)
    return report


def index_by_filename(report: Optional[ManifestReport] = None) -> Dict[str, ManifestEntry]:
    """Filename -> entry, so ingestion can attach provenance to a bare PDF."""
    report = report or load_manifest()
    index: Dict[str, ManifestEntry] = {}
    for entry in report.entries:
        if entry.filename:
            index[entry.filename.lower()] = entry
        if entry.standard_id:
            index.setdefault(f"{entry.standard_id.lower()}.pdf", entry)
            index.setdefault(f"{entry.standard_id.lower()}.txt", entry)
    return index


def register_document(
    *,
    document_id: str,
    title: str,
    is_number: str,
    local_path: str,
    source_url: str,
    document_type: str = DocumentType.STANDARD.value,
    retrieved_at: Optional[str] = None,
    source_type: str = SourceType.OFFICIAL.value,
    notes: str = "",
    product_category: str = "",
    keywords: Optional[List[str]] = None,
    covered_areas: Optional[List[str]] = None,
    path: Optional[Path] = None,
) -> ManifestEntry:
    """Add or update an official document entry, validating it first."""
    path = path or MANIFEST_PATH
    payload = (
        json.loads(path.read_text(encoding="utf-8"))
        if path.exists()
        else {"manifest_version": "1.1", "documents": []}
    )

    raw = {
        "document_id": document_id,
        "title": title,
        "is_number": is_number,
        "standard_id": document_id,
        "document_type": document_type,
        "source_url": source_url,
        "source_type": source_type,
        "is_verified": True,
        "is_demo": False,
        "retrieved_at": retrieved_at or datetime.utcnow().date().isoformat(),
        "local_path": local_path,
        "notes": notes,
        "product_category": product_category,
        "keywords": keywords or [],
        "covered_areas": covered_areas or [],
    }
    entry, errors = validate_entry(raw)
    if errors:
        raise ValueError("; ".join(errors))

    documents = [d for d in payload.get("documents", []) if d.get("document_id") != document_id]
    documents.append(entry.as_dict())
    payload["documents"] = documents
    payload["manifest_version"] = "1.1"
    payload["updated_at"] = datetime.utcnow().isoformat(timespec="seconds")
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return entry
