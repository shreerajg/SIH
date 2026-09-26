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
