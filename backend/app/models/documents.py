"""MongoDB document models for the BIS standards intelligence platform.

These are plain dataclasses, not an ORM. They exist so the rest of the
application keeps reading records by attribute (``standard.is_number``,
``clause.chunk_id``) exactly as it did under SQLAlchemy, while the storage
layer underneath is ordinary PyMongo.

Two design points carried over deliberately from the SQL schema:

* **Identifiers are application-generated strings** - ``prd-1a2b3c``,
  ``DEMO-STD-001``, ``IS-2082-2018-PM::c4.5.2``. They are stored as ``_id``
  verbatim; no ObjectIds are introduced. The vector collections are keyed by
  these same strings, so changing them would silently break retrieval.
* **Every knowledge record carries provenance** (``source_type``,
  ``is_verified``, ``is_demo``/``is_mock``) so the UI can always tell the user
  whether a fact came from an official document or the labelled demo corpus.

``ProductStandardMatch`` and ``ComplianceResult`` are **embedded** in their
product rather than kept in their own collections: both are only ever read and
written for one product at a time, and both are replaced wholesale, which an
embedded array does atomically in a single update.
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Type, TypeVar

T = TypeVar("T", bound="Document")


def _now() -> datetime:
    return datetime.utcnow()


class Document:
    """Shared ``_id`` <-> ``id`` conversion for every document model."""

    #: Sub-document lists, as {attribute: model}. Populated by subclasses that
    #: embed other documents.
    _embedded: Dict[str, type] = {}

    @classmethod
    def from_doc(cls: Type[T], doc: Optional[Dict[str, Any]]) -> Optional[T]:
        if doc is None:
            return None
        data: Dict[str, Any] = {}
        known = {f.name for f in fields(cls)}  # type: ignore[arg-type]
        for key, value in doc.items():
            name = "id" if key == "_id" else key
            if name not in known:
                # Unknown keys are ignored rather than fatal, so a document
                # written by a newer version still loads.
                continue
            embedded_model = cls._embedded.get(name)
            if embedded_model is not None and isinstance(value, list):
                value = [embedded_model.from_doc(v) for v in value if isinstance(v, dict)]
            data[name] = value
        return cls(**data)  # type: ignore[arg-type]

    def to_doc(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for f in fields(self):  # type: ignore[arg-type]
            value = getattr(self, f.name)
            if isinstance(value, list) and value and is_dataclass(value[0]):
                value = [v.to_doc() for v in value]
            out["_id" if f.name == "id" else f.name] = value
        return out


# ---------------------------------------------------------------------------
# Corpus
# ---------------------------------------------------------------------------

@dataclass
class Standard(Document):
    id: str
    is_number: str = ""
    normalized_number: str = ""
    title: str = ""
    year: Optional[int] = None
    version: Optional[str] = None
    scope: str = ""
    plain_summary: str = ""
    product_category: str = ""
    keywords: List[str] = field(default_factory=list)
    covered_areas: List[str] = field(default_factory=list)
    status: str = "active"
    source_url: str = ""
    source_type: str = "demo"
    document_id: str = ""
    document_type: str = "standard"
    document_path: str = ""
    retrieved_at: Optional[datetime] = None
    is_verified: bool = False
    #: True for the synthetic demonstration corpus. is_mock is kept as the
    #: legacy alias so existing records and callers keep working.
    is_demo: bool = True
    is_mock: bool = True
    created_at: datetime = field(default_factory=_now)


@dataclass
class StandardClause(Document):
    id: str
    standard_id: str = ""
    section_number: str = ""
    clause_number: str = ""
    heading: str = ""
    text: str = ""
    page_number: Optional[int] = None
    clause_type: str = "requirement"
    chunk_id: str = ""
    token_estimate: int = 0
    #: Structured table payload when this chunk came from a table, else empty.
    table_json: Dict[str, Any] = field(default_factory=dict)
    is_table: bool = False


@dataclass
class ComplianceRequirement(Document):
    id: str
    standard_id: str = ""
    clause_id: Optional[str] = None
    requirement_code: str = ""
    category: str = "safety"
    requirement_text: str = ""
    evidence_type: str = "document"
    severity: str = "major"
    # Optional machine-checkable rule, e.g.
    # {"attribute": "voltage", "operator": "between", "value": [200, 250]}
    check_rule_json: Dict[str, Any] = field(default_factory=dict)
    applies_when_json: Dict[str, Any] = field(default_factory=dict)
    source_clause_number: str = ""


@dataclass
class QCO(Document):
    """Quality Control Order / regulatory record.

    Regulatory status is answered from this collection only - never from the
    LLM, and never inferred from the absence of a record.
    """

    id: str
    standard_id: str = ""
    product_name: str = ""
    qco_name: str = ""
    notification_number: str = ""
    notification_date: Optional[datetime] = None
    effective_date: Optional[datetime] = None
    status: str = "MANDATORY"
    scheme: str = ""
    ministry: str = ""
    source_url: str = ""
    document_id: str = ""
    retrieved_at: Optional[datetime] = None
    is_verified: bool = False
    is_demo: bool = True
    is_mock: bool = True


@dataclass
class Amendment(Document):
    id: str
    standard_id: str = ""
    amendment_number: str = ""
    publication_date: Optional[datetime] = None
    effective_date: Optional[datetime] = None
    affected_clause: str = ""
    summary: str = ""
    old_text: str = ""
    new_text: str = ""
    source_url: str = ""
    document_id: str = ""
    retrieved_at: Optional[datetime] = None
    is_verified: bool = False
    is_demo: bool = True
    is_mock: bool = True


@dataclass
class StandardRelationship(Document):
    id: str
    source_standard_id: str = ""
    target_standard_id: str = ""
    relationship_type: str = "related"
    evidence: str = ""


# ---------------------------------------------------------------------------
# Product side
# ---------------------------------------------------------------------------

@dataclass
class ProductStandardMatch(Document):
    """Embedded in ``products.matches``.

    Uniqueness of (product, standard) - a UNIQUE constraint under SQL - is
    structural here: the array is replaced as a whole on every discovery run.
    """

    id: str
    product_id: str = ""
    standard_id: str = ""
    relevance: str = "NEEDS_VERIFICATION"
    score: float = 0.0
    reason: str = ""
    matched_attributes_json: List[Dict[str, Any]] = field(default_factory=list)
    scope_evidence: str = ""
    evidence_chunk_ids: List[str] = field(default_factory=list)
    explanation_source: str = "deterministic"
    #: Retrieval score breakdown (semantic/bm25/metadata + flags) behind
    #: `score`, kept so the "how was this ranked" visualisation survives a
    #: page reload instead of only appearing right after a live re-run.
    signals_json: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_now)


@dataclass
class ComplianceResult(Document):
    """Embedded in ``products.results``.

    Uniqueness of (product, requirement) is structural, as for matches above.
    """

    id: str
    product_id: str = ""
    requirement_id: str = ""
    status: str = "UNKNOWN"
    reason: str = ""
    evidence_id: Optional[str] = None
    confidence: float = 0.0
    recommended_action: str = ""
    decided_by: str = "rule_engine"
    created_at: datetime = field(default_factory=_now)


@dataclass
class Product(Document):
    id: str
    name: str = ""
    description: str = ""
    category: str = ""
    attributes_json: Dict[str, Any] = field(default_factory=dict)
    missing_fields_json: List[Any] = field(default_factory=list)
    profile_source: str = "deterministic"
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)
    #: Embedded children - see the module docstring.
    matches: List[ProductStandardMatch] = field(default_factory=list)
    results: List[ComplianceResult] = field(default_factory=list)

    _embedded = {"matches": ProductStandardMatch, "results": ComplianceResult}


@dataclass
class ProductEvidence(Document):
    """Kept in its own collection rather than embedded in the product.

    ``extracted_text`` holds up to 200 KB per document, and evidence is
    addressed individually by id (fetch/delete endpoints), so embedding it
    would risk the 16 MB document ceiling for no gain.
    """

    id: str
    product_id: str = ""
    evidence_type: str = "declared_value"
    name: str = ""
    value: str = ""
    file_path: str = ""
    original_filename: str = ""
    content_type: str = ""
    size_bytes: int = 0
    upload_category: str = "other"
    #: Text extracted from an uploaded PDF/label, used for evidence matching.
    extracted_text: str = ""
    #: Structured values pulled out of the document (model, ratings, results).
    extracted_fields_json: Dict[str, Any] = field(default_factory=dict)
    extraction_status: str = "none"
    metadata_json: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_now)


@dataclass
class CertificationScheme(Document):
    """A BIS certification scheme (Scheme-I / ISI Mark, CRS, Hallmarking, ...).

    Descriptive fields are only populated where they could be sourced from an
    official BIS document; ``field_sources`` records where each one came from.
    An unsourced field is left empty and reported to the user as "unable to
    verify" rather than filled in with plausible-sounding prose.

    This record never decides *applicability* - that is resolved from stored QCO
    records and the extracted BIS Scheme-I product list.
    """

    id: str
    code: str = ""
    name: str = ""
    aliases: List[str] = field(default_factory=list)
    mark: str = ""
    purpose: str = ""
    applies_to: str = ""
    product_applicability: str = ""
    legal_basis: str = ""
    testing_requirement: str = ""
    key_documents: List[str] = field(default_factory=list)
    process_url: str = ""
    source_url: str = ""
    document_id: str = ""
    retrieved_at: Optional[str] = None
    is_verified: bool = False
    is_demo: bool = False
    #: {field_name: where that field's content came from}
    field_sources: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CertificationProcess(Document):
    """The stage template for one scheme's certification journey.

    Stages describe what happens; they carry no quoted source text. The clause
    that supports a stage is resolved at query time against the documents held
    for the specific standard, so a citation is always live rather than copied
    into this record.
    """

    id: str
    scheme_id: str = ""
    title: str = ""
    summary: str = ""
    process_url: str = ""
    stages: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class SchemeProductEntry(Document):
    """One row of the official BIS Scheme-I product list.

    Presence of a standard here is the evidence that it is covered by Scheme-I.
    Absence is reported as "unable to verify", never as "not covered" - the list
    is a snapshot of one BIS page, not a complete statement of Indian law.
    """

    id: str
    scheme_id: str = ""
    is_number: str = ""
    normalized_number: str = ""
    product: str = ""
    product_group: str = ""
    notification: str = ""
    source_url: str = ""
    document_id: str = ""
    retrieved_at: Optional[str] = None
    is_verified: bool = True


# ---------------------------------------------------------------------------
# Hallmarking
# ---------------------------------------------------------------------------

@dataclass
class HallmarkingKnowledge(Document):
    """One structured hallmarking fact, transcribed from an official BIS source.

    ``clause_keywords`` is how the record earns its citation: at query time the
    service finds the clause in the ingested BIS document that literally
    contains one of them, so the evidence shown is live corpus text rather than
    a copy that could drift. A record whose keywords match nothing is reported
    as unverified instead of being shown bare.

    ``kind`` partitions the collection: purity_grade | hallmark_component |
    consumer_check | process_stage | scheme | huid.
    """

    id: str
    kind: str = ""
    order: int = 0
    payload: Dict[str, Any] = field(default_factory=dict)
    clause_keywords: List[str] = field(default_factory=list)
    source_document_id: str = ""
    prefer_document_ids: List[str] = field(default_factory=list)


@dataclass
class HallmarkingCentre(Document):
    """A BIS recognised Assaying & Hallmarking Centre.

    Transcribed from the directory BIS publishes on the HUID portal. ``status``
    is carried through verbatim - a suspended centre is shown as suspended
    rather than filtered out silently - and ``retrieved_at`` is always exposed,
    because recognition can lapse between snapshots.
    """

    id: str
    recognition_number: str = ""
    name: str = ""
    address: str = ""
    city: str = ""
    state: str = ""
    pin: str = ""
    scope: str = ""
    status: str = ""
    validity: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    source_url: str = ""
    document_id: str = ""
    retrieved_at: Optional[str] = None
    is_verified: bool = True


@dataclass
class IngestionRun(Document):
    """Bookkeeping so the UI can show what is actually in the corpus."""

    id: str
    started_at: datetime = field(default_factory=_now)
    finished_at: Optional[datetime] = None
    documents: int = 0
    chunks: int = 0
    embedding_backend: str = ""
    vector_backend: str = ""
    notes: str = ""
