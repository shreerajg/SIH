"""Typed API contracts.

The frontend never parses raw model output: every LLM result is converted into
one of these objects (and validated) inside the backend first.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.core.constants import (
    AmendmentRelevance,
    ComplianceStatus,
    QueryType,
    RegulatoryStatus,
    Relevance,
    SchemeApplicability,
    VerificationState,
)


# ---------------------------------------------------------------------------
# Health / meta
# ---------------------------------------------------------------------------

class CorpusStats(BaseModel):
    #: The configured policy: which documents retrieval is allowed to use.
    corpus_mode: str = "MIXED"
    corpus_mode_label: str = "Mixed Corpus"
    corpus_mode_message: str = ""
    #: What the corpus actually holds, derived from the loaded documents.
    #: DEMO / VERIFIED / MIXED / EMPTY - not the same question as the policy.
    corpus_content_mode: str = "EMPTY"
    corpus_content_label: str = "Empty Corpus"
    usable_standards: int = 0
    starved: bool = False
    tables: int = 0
    standards: int = 0
    clauses: int = 0
    requirements: int = 0
    regulatory_records: int = 0
    amendments: int = 0
    relationships: int = 0
    vectors_standards: int = 0
    vectors_clauses: int = 0
    dataset_status: str = "demo"
    verified_standards: int = 0
    demo_standards: int = 0


class HealthResponse(BaseModel):
    status: str
    app: str
    environment: str
    database: Dict[str, Any]
    llm: Dict[str, Any]
    retrieval: Dict[str, Any]
    corpus: CorpusStats
    regulatory: Dict[str, Any] = Field(default_factory=dict)
    disclaimer: str


# ---------------------------------------------------------------------------
# Product understanding
# ---------------------------------------------------------------------------

class ProductAnalyzeRequest(BaseModel):
    description: str = Field(min_length=3, max_length=4000)
    name: Optional[str] = None


class MissingField(BaseModel):
    field: str
    question: str
    why_it_matters: str
    options: List[str] = Field(default_factory=list)
    input_type: str = "choice"
    unit: Optional[str] = None
    #: 1 = decides which standards apply; 2 = sharpens the gap analysis.
    priority: int = 1


class ProductProfile(BaseModel):
    id: str
    name: str
    description: str
    category: str
    attributes: Dict[str, Any] = Field(default_factory=dict)
    missing_fields: List[MissingField] = Field(default_factory=list)
    profile_source: str = "deterministic"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ProductAnalyzeResponse(BaseModel):
    product: ProductProfile
    interview_required: bool
    notes: List[str] = Field(default_factory=list)
    llm_used: bool = False


class InterviewAnswer(BaseModel):
    field: str
    value: Any


class InterviewRequest(BaseModel):
    answers: List[InterviewAnswer] = Field(default_factory=list)
    skip_remaining: bool = False


# ---------------------------------------------------------------------------
# Standards
# ---------------------------------------------------------------------------

class RegulatoryEvidence(BaseModel):
    """The stored record behind a regulatory status, shown in the evidence drawer."""

    qco_name: Optional[str] = None
    notification_number: Optional[str] = None
    notification_date: Optional[str] = None
    effective_date: Optional[str] = None
    declared_status: str = ""
    effective_status: str = ""
    scheme: Optional[str] = None
    ministry: Optional[str] = None
    source_url: Optional[str] = None
    document_id: Optional[str] = None
    retrieved_at: Optional[str] = None
    is_verified: bool = False
    is_demo: bool = True
    product_name: Optional[str] = None


class RegulatoryStatusInfo(BaseModel):
    status: RegulatoryStatus
    verified: bool = False
    source: Optional[str] = None
    qco_name: Optional[str] = None
    notification_number: Optional[str] = None
    notification_date: Optional[str] = None
    effective_date: Optional[str] = None
    ministry: Optional[str] = None
    scheme: Optional[str] = None
    source_url: Optional[str] = None
    is_mock: bool = True
    message: str
    evidence: Optional[RegulatoryEvidence] = None


class SchemeEvidence(BaseModel):
    """One stored record behind a scheme determination."""

    kind: str                      # qco_record | scheme_product_list
    label: str
    detail: str = ""
    source_url: Optional[str] = None
    document_id: Optional[str] = None
    is_verified: bool = False
    retrieved_at: Optional[str] = None


class SchemeReason(BaseModel):
    """One factor in why a scheme was returned."""

    factor: str
    detail: str
    source: str
    is_verified: bool = False


class SchemeInfo(BaseModel):
    """A registered BIS certification scheme.

    Descriptive fields are Optional and are None where the content was never
    sourced from an official BIS document; ``unavailable_fields`` names those
    and ``unavailable_note`` is what the UI should show in their place.
    """

    id: str
    code: str
    name: str
    mark: Optional[str] = None
    purpose: Optional[str] = None
    applies_to: Optional[str] = None
    product_applicability: Optional[str] = None
    legal_basis: Optional[str] = None
    testing_requirement: Optional[str] = None
    key_documents: List[str] = Field(default_factory=list)
    process_url: Optional[str] = None
    source_url: Optional[str] = None
    document_id: Optional[str] = None
    retrieved_at: Optional[str] = None
    is_verified: bool = False
    field_sources: Dict[str, Any] = Field(default_factory=dict)
    unavailable_fields: List[str] = Field(default_factory=list)
    unavailable_note: str = ""


class SchemeGuidance(BaseModel):
    """The answer to "which scheme applies, and why"."""

    applicability: SchemeApplicability
    scheme: Optional[SchemeInfo] = None
    standard_id: Optional[str] = None
    reasons: List[SchemeReason] = Field(default_factory=list)
    evidence: List[SchemeEvidence] = Field(default_factory=list)
    regulatory: Optional["RegulatoryStatusInfo"] = None
    message: str = ""


# ---------------------------------------------------------------------------
# Hallmarking
# ---------------------------------------------------------------------------

class HallmarkFact(BaseModel):
    """One hallmarking fact plus the clause that supports it.

    ``evidence`` is live corpus text. When it is None the fact could not be
    tied to a clause in the ingested BIS documents, ``state`` says
    UNABLE_TO_VERIFY and ``note`` explains - the fact is never shown as though
    it were sourced.
    """

    id: str
    text: str = ""
    detail: Dict[str, Any] = Field(default_factory=dict)
    state: VerificationState = VerificationState.UNABLE_TO_VERIFY
    evidence: Optional[ClauseRef] = None
    source_url: Optional[str] = None
    note: str = ""


class PurityGrade(BaseModel):
    id: str
    material: str
    carat: Optional[str] = None
    fineness: Optional[str] = None
    permitted_marking: Optional[str] = None
    #: True where the mandatory hallmarking order names this grade.
    mandatory_order_covered: bool = False
    note: Optional[str] = None
    state: VerificationState = VerificationState.UNABLE_TO_VERIFY
    evidence: Optional[ClauseRef] = None


class HallmarkComponent(BaseModel):
    id: str
    order: int = 0
    name: str
    description: str = ""
    applies_to: List[str] = Field(default_factory=list)
    state: VerificationState = VerificationState.UNABLE_TO_VERIFY
    evidence: Optional[ClauseRef] = None


class HuidGuidance(BaseModel):
    """What a HUID is, and what this platform can and cannot do with one."""

    available: bool = False
    length: Optional[int] = None
    character_set: Optional[str] = None
    description: str = ""
    in_force_from: Optional[str] = None
    state: VerificationState = VerificationState.UNABLE_TO_VERIFY
    evidence: Optional[ClauseRef] = None
    #: Always false here. Live HUID verification is not integrated, so the
    #: platform must never present a HUID as checked.
    live_verification_available: bool = False
    verification_note: str = ""
    official_verification_url: Optional[str] = None


class HallmarkingOverview(BaseModel):
    available: bool = False
    name: str = ""
    summary: str = ""
    operated_by: Optional[str] = None
    materials: List[str] = Field(default_factory=list)
    legal_basis: Optional[str] = None
    state: VerificationState = VerificationState.UNABLE_TO_VERIFY
    evidence: Optional[ClauseRef] = None
    source_url: Optional[str] = None
    standards: List[HallmarkFact] = Field(default_factory=list)
    message: str = ""
    disclaimer: str = ""


class ConsumerHallmarkGuide(BaseModel):
    available: bool = False
    material: str = "gold"
    overview: Optional[HallmarkingOverview] = None
    components: List[HallmarkComponent] = Field(default_factory=list)
    purity_grades: List[PurityGrade] = Field(default_factory=list)
    checks: List[HallmarkFact] = Field(default_factory=list)
    huid: Optional[HuidGuidance] = None
    facts_with_evidence: int = 0
    message: str = ""
    disclaimer: str = ""


class HallmarkProcessStage(BaseModel):
    id: str
    order: int
    title: str
    actor: str                 # jeweller | ahc | bis | both
    summary: str = ""
    what_you_do: List[str] = Field(default_factory=list)
    state: VerificationState = VerificationState.UNABLE_TO_VERIFY
    evidence: Optional[ClauseRef] = None
    evidence_note: str = ""


class JewellerHallmarkGuide(BaseModel):
    available: bool = False
    title: str = ""
    summary: str = ""
    stages: List[HallmarkProcessStage] = Field(default_factory=list)
    stages_with_evidence: int = 0
    centre_summary: "CentreDirectorySummary"
    message: str = ""
    disclaimer: str = ""


class AssayingCentre(BaseModel):
    recognition_number: str
    name: str
    city: Optional[str] = None
    state: Optional[str] = None
    pin: Optional[str] = None
    scope: Optional[str] = None
    status: str = ""
    validity: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None


class CentreDirectorySummary(BaseModel):
    """What the local A&H centre snapshot holds, and how stale it may be."""

    available: bool = False
    total: int = 0
    operative: int = 0
    states: List[str] = Field(default_factory=list)
    source_url: Optional[str] = None
    retrieved_at: Optional[str] = None
    note: str = ""


class CentreSearchResponse(BaseModel):
    summary: CentreDirectorySummary
    results: List[AssayingCentre] = Field(default_factory=list)
    total_matching: int = 0
    message: str = ""


class ProcessStage(BaseModel):
    """One step of a certification journey.

    ``evidence`` is the clause in this product's own documents that supports
    the stage. It is None when nothing in the corpus backs the stage, and
    ``evidence_note`` then says so - a stage is never padded with prose that has
    no source.
    """

    id: str
    order: int
    title: str
    actor: str                     # manufacturer | bis | both
    summary: str
    what_you_do: List[str] = Field(default_factory=list)
    documents: List[str] = Field(default_factory=list)
    evidence: Optional[ClauseRef] = None
    evidence_note: str = ""
    #: True for stages whose source document this platform does not hold.
    external: bool = False
    external_url: Optional[str] = None


class ComplianceDeadline(BaseModel):
    """An implementation date read from a Quality Control Order table."""

    enterprise_category: str
    date: str
    standard: Optional[str] = None
    product: Optional[str] = None


class ComplianceTimeline(BaseModel):
    """Implementation dates, which differ by enterprise size.

    Read from the QCO's own table, so an MSME sees the date that applies to it
    rather than the general one.
    """

    available: bool = False
    deadlines: List[ComplianceDeadline] = Field(default_factory=list)
    evidence: Optional[ClauseRef] = None
    note: str = ""


class ProcessGuidance(BaseModel):
    scheme_id: Optional[str] = None
    scheme_name: Optional[str] = None
    standard_id: Optional[str] = None
    title: str = ""
    summary: str = ""
    process_url: Optional[str] = None
    stages: List[ProcessStage] = Field(default_factory=list)
    timeline: ComplianceTimeline = Field(default_factory=ComplianceTimeline)
    #: How many stages could be backed by a clause in the corpus.
    stages_with_evidence: int = 0
    available: bool = False
    message: str = ""
    disclaimer: str = ""


class ProductSchemeGuidance(BaseModel):
    product_id: str
    primary: Optional[SchemeGuidance] = None
    per_standard: List[SchemeGuidance] = Field(default_factory=list)
    note: str = ""
    disclaimer: str = ""


class StandardSummary(BaseModel):
    id: str
    is_number: str
    display_number: str
    title: str
    year: Optional[int] = None
    version: Optional[str] = None
    product_category: str = ""
    covered_areas: List[str] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)
    source_type: str = "demo"
    source_url: Optional[str] = None
    is_verified: bool = False
    is_mock: bool = True
    #: standard / product_manual / qco / amendment / regulatory. The verified
    #: corpus holds official supporting documents, not full Indian Standard
    #: texts, and every surface that shows a document must say which it is.
    document_type: str = "standard"
    retrieved_at: Optional[str] = None
    clause_count: int = 0
    requirement_count: int = 0


class ClauseRef(BaseModel):
    chunk_id: str
    standard_id: str
    is_number: str
    display_number: str
    version: Optional[str] = None
    clause_number: str
    heading: str = ""
    page_number: Optional[int] = None
    clause_type: str = "requirement"
    excerpt: str
    source_url: Optional[str] = None
    is_verified: bool = False
    #: What kind of document this text actually came from - a full Indian
    #: Standard, a BIS Product Manual, a QCO, an amendment, a gazette
    #: notification. A citation that does not say this can let Product Manual
    #: text be read as Standard clause text, which is exactly the confusion
    #: the verified corpus must not introduce.
    document_type: str = "standard"
    #: The title of the source document, so a citation can name the manual or
    #: order it came from rather than only the standard it relates to.
    document_title: str = ""
    relevance_score: Optional[float] = None


class MatchedAttribute(BaseModel):
    attribute: str
    product_value: str
    matched_on: str
    note: str = ""


class StandardMatch(BaseModel):
    standard: StandardSummary
    relevance: Relevance
    reason: str
    matched_attributes: List[MatchedAttribute] = Field(default_factory=list)
    scope_evidence: str = ""
    evidence_clauses: List[ClauseRef] = Field(default_factory=list)
    regulatory: RegulatoryStatusInfo
    explanation_source: str = "deterministic"
    #: The combined retrieval score signals were blended into (0-1).
    score: float = 0.0
    signals: Dict[str, Any] = Field(default_factory=dict)


class DiscoverStandardsResponse(BaseModel):
    product_id: str
    matches: List[StandardMatch]
    candidates_considered: int
    llm_used: bool = False
    notes: List[str] = Field(default_factory=list)
    disclaimer: str


class StandardDetail(BaseModel):
    standard: StandardSummary
    scope: str
    plain_summary: str
    regulatory: RegulatoryStatusInfo
    clauses: List[ClauseRef] = Field(default_factory=list)
    requirement_categories: Dict[str, int] = Field(default_factory=dict)
    related: List[Dict[str, Any]] = Field(default_factory=list)
    amendments: List["AmendmentInfo"] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# RAG
# ---------------------------------------------------------------------------

class RAGRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    standard_ids: List[str] = Field(default_factory=list)
    product_id: Optional[str] = None
    query_type: Optional[QueryType] = None
    #: Pass the id returned by the previous answer to ask a grounded follow-up.
    conversation_id: Optional[str] = None


class Claim(BaseModel):
    text: str
    source_chunk_ids: List[str] = Field(default_factory=list)
    supported: bool = True


class EvidenceShieldReport(BaseModel):
    verified: bool
    total_claims: int
    supported_claims: int
    rejected_claims: List[Dict[str, Any]] = Field(default_factory=list)
    retrieved_chunk_ids: List[str] = Field(default_factory=list)
    reason: str = ""


class RAGResponse(BaseModel):
    question: str
    query_type: QueryType
    answer: str
    answerable: bool
    claims: List[Claim] = Field(default_factory=list)
    citations: List[ClauseRef] = Field(default_factory=list)
    evidence_shield: EvidenceShieldReport
    regulatory: Optional[RegulatoryStatusInfo] = None
    #: Present on CERTIFICATION_QUERY answers: the resolved determination and
    #: the scheme it names, so the UI can render the same card the discovery
    #: flow shows instead of re-deriving it from prose.
    scheme_guidance: Optional[SchemeGuidance] = None
    scheme: Optional[SchemeInfo] = None
    #: Present when the question asked *how* to get certified rather than
    #: which scheme applies.
    process_guidance: Optional[ProcessGuidance] = None
    standards_searched: List[str] = Field(default_factory=list)
    llm_used: bool = False
    conversation_id: Optional[str] = None
    follow_up: bool = False
    scope_note: str = ""
    reranker: str = ""
    disclaimer: str


# ---------------------------------------------------------------------------
# Compliance
# ---------------------------------------------------------------------------

class EvidenceInput(BaseModel):
    evidence_type: str
    name: str
    value: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ComplianceAnalyzeRequest(BaseModel):
    attributes: Dict[str, Any] = Field(default_factory=dict)
    evidence: List[EvidenceInput] = Field(default_factory=list)
    standard_ids: List[str] = Field(default_factory=list)


class RequirementResult(BaseModel):
    requirement_id: str
    requirement_code: str
    requirement_text: str
    category: str
    severity: str
    evidence_type: str
    status: ComplianceStatus
    reason: str
    recommended_action: str = ""
    confidence: float = 0.0
    decided_by: str = "rule_engine"
    matched_evidence: Optional[str] = None
    #: The specific uploaded/declared evidence row backing matched_evidence,
    #: when there is one - lets a caller link straight to what was supplied.
    matched_evidence_id: Optional[str] = None
    source: ClauseRef


class ReadinessSummary(BaseModel):
    label: str = "Pre-Compliance Readiness"
    percentage: int = 0
    supported: int = 0
    assessable: int = 0
    total_requirements: int = 0
    tooltip: str
    by_status: Dict[str, int] = Field(default_factory=dict)
    by_category: Dict[str, Dict[str, int]] = Field(default_factory=dict)


class ComplianceResponse(BaseModel):
    product_id: str
    product_name: str
    generated_at: Optional[datetime] = None
    standards: List[StandardSummary] = Field(default_factory=list)
    results: List[RequirementResult] = Field(default_factory=list)
    readiness: ReadinessSummary
    evidence_provided: List[Dict[str, Any]] = Field(default_factory=list)
    llm_used: bool = False
    disclaimer: str


class ComplianceTwinResponse(BaseModel):
    product: ProductProfile
    summary: Dict[str, Any]
    readiness: ReadinessSummary
    standards: List[StandardMatch] = Field(default_factory=list)
    results: List[RequirementResult] = Field(default_factory=list)
    testing_plan: List[Dict[str, Any]] = Field(default_factory=list)
    evidence: List[Dict[str, Any]] = Field(default_factory=list)
    amendments: List["AmendmentImpact"] = Field(default_factory=list)
    graph: Dict[str, Any] = Field(default_factory=dict)
    sources: List[Dict[str, Any]] = Field(default_factory=list)
    analysis_available: bool = False
    disclaimer: str


# ---------------------------------------------------------------------------
# Amendments
# ---------------------------------------------------------------------------

class DiffSegment(BaseModel):
    op: str  # equal | insert | delete
    text: str


class AmendmentInfo(BaseModel):
    id: str
    standard_id: str
    is_number: str
    display_number: str
    amendment_number: str
    publication_date: Optional[str] = None
    effective_date: Optional[str] = None
    affected_clause: str
    summary: str
    old_text: str
    new_text: str
    is_verified: bool = False
    is_mock: bool = True
    source_url: Optional[str] = None


class ProductAmendmentImpact(BaseModel):
    """How an amendment relates to one product. Never a compliance verdict."""

    relevance: AmendmentRelevance
    reason: str
    affected_requirement_codes: List[str] = Field(default_factory=list)
    supported_requirement_codes: List[str] = Field(default_factory=list)


class AmendmentImpact(BaseModel):
    amendment: AmendmentInfo
    diff: List[DiffSegment] = Field(default_factory=list)
    changed_numbers: List[Dict[str, Any]] = Field(default_factory=list)
    potential_impact: str
    impact_source: str = "deterministic"
    affected_requirements: List[str] = Field(default_factory=list)
    product_impact: Optional[ProductAmendmentImpact] = None


# ---------------------------------------------------------------------------
# Consumer
# ---------------------------------------------------------------------------

class ConsumerLookupRequest(BaseModel):
    query: str = Field(min_length=1, max_length=120)


class ConsumerStandardResponse(BaseModel):
    found: bool
    query: str
    normalized_query: str = ""
    standard: Optional[StandardSummary] = None
    what_is_it: str = ""
    what_it_covers: List[str] = Field(default_factory=list)
    why_it_matters: str = ""
    applies_to: str = ""
    regulatory: Optional[RegulatoryStatusInfo] = None
    sources: List[ClauseRef] = Field(default_factory=list)
    suggestions: List[StandardSummary] = Field(default_factory=list)
    message: str = ""
    llm_used: bool = False
    disclaimer: str = ""


class SourceDetail(BaseModel):
    chunk_id: str
    standard: StandardSummary
    clause_number: str
    heading: str
    page_number: Optional[int] = None
    text: str
    neighbours: List[ClauseRef] = Field(default_factory=list)


StandardDetail.model_rebuild()
ComplianceTwinResponse.model_rebuild()

JewellerHallmarkGuide.model_rebuild()
