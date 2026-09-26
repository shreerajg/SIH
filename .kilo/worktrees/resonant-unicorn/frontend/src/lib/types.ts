/** Types mirroring the backend Pydantic contracts (app/schemas/models.py). */

export type Relevance = 'HIGH' | 'MEDIUM' | 'LOW' | 'NEEDS_VERIFICATION'

export type ComplianceStatus =
  | 'SUPPORTED'
  | 'POTENTIAL_GAP'
  | 'TEST_REQUIRED'
  | 'DOCUMENT_REQUIRED'
  | 'UNKNOWN'
  | 'NOT_APPLICABLE'
  | 'OFFICIAL_VERIFICATION_REQUIRED'

export type RegulatoryStatusValue =
  | 'MANDATORY'
  | 'UPCOMING'
  | 'WITHDRAWN'
  | 'VOLUNTARY'
  | 'UNABLE_TO_VERIFY'

export type CorpusModeValue = 'DEMO' | 'VERIFIED' | 'MIXED'

export interface RegulatoryEvidence {
  qco_name: string | null
  notification_number: string | null
  notification_date: string | null
  effective_date: string | null
  declared_status: string
  effective_status: string
  scheme: string | null
  ministry: string | null
  source_url: string | null
  document_id: string | null
  retrieved_at: string | null
  is_verified: boolean
  is_demo: boolean
  product_name: string | null
}

export interface RegulatoryDetail {
  standard_id: string
  status: RegulatoryStatusInfo
  history: RegulatoryEvidence[]
  note: string
}

export interface CorpusStats {
  corpus_mode: CorpusModeValue
  corpus_mode_label: string
  corpus_mode_message: string
  /** What the corpus actually holds, as opposed to the configured policy. */
  corpus_content_mode: CorpusModeValue | 'EMPTY'
  corpus_content_label: string
  usable_standards: number
  starved: boolean
  tables: number
  standards: number
  clauses: number
  requirements: number
  regulatory_records: number
  amendments: number
  relationships: number
  vectors_standards: number
  vectors_clauses: number
  dataset_status: string
  verified_standards: number
  demo_standards: number
}

export interface HealthResponse {
  status: string
  app: string
  environment: string
  database: { backend: string; url: string }
  llm: {
    available: boolean
    mode: string
    provider: string
    model: string | null
    fallback_mode: boolean
    supported_providers?: string[]
    last_error?: string | null
    note: string
  }
  retrieval: {
    embedding_backend: string
    embedding_dimension: number
    vector_backend: string
    keyword_backend: string
    reranker?: string
    weights: Record<string, number>
  }
  corpus: CorpusStats
  regulatory?: Record<string, unknown>
  disclaimer: string
}

export interface MissingField {
  field: string
  question: string
  why_it_matters: string
  options: string[]
  input_type: string
  unit: string | null
  priority?: number
}

export interface ProductProfile {
  id: string
  name: string
  description: string
  category: string
  attributes: Record<string, unknown>
  missing_fields: MissingField[]
  profile_source: string
  created_at?: string | null
  updated_at?: string | null
}

export interface ProductAnalyzeResponse {
  product: ProductProfile
  interview_required: boolean
  notes: string[]
  llm_used: boolean
}

export interface RegulatoryStatusInfo {
  status: RegulatoryStatusValue
  verified: boolean
  source: string | null
  qco_name: string | null
  notification_number: string | null
  notification_date: string | null
  effective_date: string | null
  ministry: string | null
  scheme?: string | null
  source_url: string | null
  is_mock: boolean
  message: string
  evidence?: RegulatoryEvidence | null
}

export interface StandardSummary {
  id: string
  is_number: string
  display_number: string
  title: string
  year: number | null
  version: string | null
  product_category: string
  covered_areas: string[]
  keywords: string[]
  source_type: string
  source_url: string | null
  is_verified: boolean
  is_mock: boolean
  /** standard / product_manual / qco / amendment / regulatory */
  document_type: string
  retrieved_at: string | null
  clause_count: number
  requirement_count: number
}

export interface ClauseRef {
  chunk_id: string
  standard_id: string
  is_number: string
  display_number: string
  version: string | null
  clause_number: string
  heading: string
  page_number: number | null
  clause_type: string
  excerpt: string
  source_url: string | null
  is_verified: boolean
  /** What kind of document this text came from. A BIS Product Manual or a QCO
   *  must never be read as full Indian Standard clause text. */
  document_type: string
  document_title: string
  relevance_score: number | null
}

export interface MatchedAttribute {
  attribute: string
  product_value: string
  matched_on: string
  note: string
}

export interface StandardMatch {
  standard: StandardSummary
  relevance: Relevance
  reason: string
  matched_attributes: MatchedAttribute[]
  scope_evidence: string
  evidence_clauses: ClauseRef[]
  regulatory: RegulatoryStatusInfo
  explanation_source: string
  score: number
  signals: Record<string, unknown>
}

export interface DiscoverStandardsResponse {
  product_id: string
  matches: StandardMatch[]
  candidates_considered: number
  llm_used: boolean
  notes: string[]
  disclaimer: string
}

export interface Claim {
  text: string
  source_chunk_ids: string[]
  supported: boolean
}

export interface EvidenceShieldReport {
  verified: boolean
  total_claims: number
  supported_claims: number
  rejected_claims: { claim: string; invalid_chunk_ids: string[]; reason: string }[]
  retrieved_chunk_ids: string[]
  reason: string
}

export interface RAGResponse {
  question: string
  query_type: string
  answer: string
  answerable: boolean
  claims: Claim[]
  citations: ClauseRef[]
  evidence_shield: EvidenceShieldReport
  regulatory: RegulatoryStatusInfo | null
  standards_searched: string[]
  llm_used: boolean
  conversation_id: string | null
  follow_up: boolean
  scope_note: string
  reranker: string
  disclaimer: string
}

export interface RequirementResult {
  requirement_id: string
  requirement_code: string
  requirement_text: string
  category: string
  severity: string
  evidence_type: string
  status: ComplianceStatus
  reason: string
  recommended_action: string
  confidence: number
  decided_by: string
  matched_evidence: string | null
  matched_evidence_id: string | null
  source: ClauseRef
}

export interface ReadinessSummary {
  label: string
  percentage: number
  supported: number
  assessable: number
  total_requirements: number
  tooltip: string
  by_status: Record<string, number>
  by_category: Record<string, Record<string, number>>
}

export interface ComplianceResponse {
  product_id: string
  product_name: string
  generated_at: string | null
  standards: StandardSummary[]
  results: RequirementResult[]
  readiness: ReadinessSummary
  evidence_provided: EvidenceRecord[]
  llm_used: boolean
  disclaimer: string
}

export interface EvidenceRecord {
  id: string
  evidence_type: string
  name: string
  value: string
  metadata: Record<string, unknown>
  created_at: string | null
}

export type UploadCategory =
  | 'datasheet'
  | 'test_report'
  | 'product_label'
  | 'technical_document'
  | 'certificate'
  | 'other'

export interface ExtractedFields {
  model: string | null
  test_names: string[]
  result: string | null
  ratings: Record<string, number>
  numeric_results: { label: string; value: number; unit: string }[]
  laboratory: string | null
  report_number: string | null
  issued_on: string | null
}

export interface UploadedEvidence {
  id: string
  name: string
  evidence_type: string
  upload_category: UploadCategory
  original_filename: string
  content_type: string
  size_bytes: number
  extraction_status: string
  extracted_fields: ExtractedFields
  has_text: boolean
  created_at: string | null
  note: string
  /** Only present on the single-record GET. */
  extracted_text_preview?: string
}

export interface EvidenceListResponse {
  product_id: string
  evidence: UploadedEvidence[]
  categories: UploadCategory[]
  note: string
}

export interface DiffSegment {
  op: 'equal' | 'insert' | 'delete'
  text: string
}

export interface AmendmentInfo {
  id: string
  standard_id: string
  is_number: string
  display_number: string
  amendment_number: string
  publication_date: string | null
  effective_date: string | null
  affected_clause: string
  summary: string
  old_text: string
  new_text: string
  is_verified: boolean
  is_mock: boolean
  source_url: string | null
}

export type AmendmentRelevance =
  | 'LIKELY_RELEVANT'
  | 'REQUIRES_REVIEW'
  | 'NO_DIRECT_MATCH_FOUND'
  | 'UNABLE_TO_VERIFY'

export interface ProductAmendmentImpact {
  relevance: AmendmentRelevance
  reason: string
  affected_requirement_codes: string[]
  supported_requirement_codes: string[]
}

export interface AmendmentImpact {
  amendment: AmendmentInfo
  diff: DiffSegment[]
  changed_numbers: { unit: string | null; old: string | null; new: string | null; direction: string }[]
  potential_impact: string
  impact_source: string
  affected_requirements: string[]
  product_impact: ProductAmendmentImpact | null
}

export interface GraphNode {
  id: string
  type: string
  label: string
  title?: string
  relevance?: string
  regulatory?: string
  standard_id?: string
  category?: string
  is_demo?: boolean
  clause_count?: number
  requirement_count?: number
  ministry?: string
}

export interface GraphEdge {
  source: string
  target: string
  type: string
  label: string
  evidence?: string
  is_demo?: boolean
}

export interface RelationshipType {
  type: string
  label: string
  description: string
}

export interface StandardsGraphResponse {
  nodes: GraphNode[]
  edges: GraphEdge[]
  categories: string[]
  relationship_types: RelationshipType[]
  focus: string
  stats: {
    standards: number
    regulatory_nodes: number
    edges: number
    relationship_types: number
  }
  available: boolean
  note: string
}

export interface TestMethodReference {
  standard_id: string
  standard: string
  evidence: string
}

export interface TestPlanItem {
  requirement_code: string
  test: string
  standard: string
  clause: string
  status: ComplianceStatus
  severity: string
  action: string
  chunk_id: string
  matched_evidence: string | null
  evidence_id: string | null
  test_method_reference: TestMethodReference | null
}

export interface ComplianceTwinResponse {
  product: ProductProfile
  summary: Record<string, number>
  readiness: ReadinessSummary
  standards: StandardMatch[]
  results: RequirementResult[]
  testing_plan: TestPlanItem[]
  evidence: EvidenceRecord[]
  amendments: AmendmentImpact[]
  graph: { nodes: GraphNode[]; edges: GraphEdge[]; available: boolean }
  sources: ClauseRef[]
  analysis_available: boolean
  disclaimer: string
}

export interface ConsumerStandardResponse {
  found: boolean
  query: string
  normalized_query: string
  standard: StandardSummary | null
  what_is_it: string
  what_it_covers: string[]
  why_it_matters: string
  applies_to: string
  regulatory: RegulatoryStatusInfo | null
  sources: ClauseRef[]
  suggestions: StandardSummary[]
  message: string
  llm_used: boolean
  disclaimer: string
}

export interface OcrScanResponse {
  ocr_available: boolean
  status: 'unavailable' | 'extracted' | 'no_text_found' | 'failed'
  raw_text: string
  candidates: string[]
  note: string
  result: ConsumerStandardResponse | null
  disclaimer: string
}

export interface ConsumerCategory {
  key: string
  label: string
  standard_count: number
}

export interface ConsumerCategoriesResponse {
  categories: ConsumerCategory[]
  note: string
}

export interface PlainFinding {
  key: string
  text: string
  chunk_id: string
  clause_number: string
  page_number: number | null
  document_type: string
}

export interface FindingsResponse {
  standard_id: string
  document_type: string
  findings: PlainFinding[]
  note: string
}

export interface StandardRequirement {
  id: string
  requirement_code: string
  category: string
  requirement_text: string
  evidence_type: string
  severity: string
  source_clause_number: string
}

export interface StandardRequirementsResponse {
  standard_id: string
  requirements: StandardRequirement[]
}

export interface SourceDetail {
  chunk_id: string
  standard: StandardSummary
  clause_number: string
  heading: string
  page_number: number | null
  text: string
  neighbours: ClauseRef[]
}

export interface StandardDetail {
  standard: StandardSummary
  scope: string
  plain_summary: string
  regulatory: RegulatoryStatusInfo
  clauses: ClauseRef[]
  requirement_categories: Record<string, number>
  related: {
    standard_id: string
    is_number: string
    title: string
    relationship_type: string
    evidence: string
  }[]
  amendments: AmendmentInfo[]
}

export interface TrustResponse {
  dataset: {
    standards: number
    verified: number
    demo: number
    standards_with_regulatory_record: number
    standards_without_regulatory_record: number
    status: string
  }
  controls: { name: string; what: string; enforced_in: string }[]
  retrieval: {
    strategy: string
    stage_1: string
    stage_2: string
    weights: Record<string, number>
  }
  llm: HealthResponse['llm']
  disclaimer: string
}

/** A metric category's outcome from scripts/evaluate.py: a real number, or an
 * honest null when it could not be computed - never a fabricated figure. */
export interface EvalMetric {
  cases: number
  [metric: string]: number | string | boolean | null | Record<string, unknown>[]
}

export interface EvaluationResults {
  available: boolean
  message?: string
  generated_at?: string
  corpus?: string
  duration_seconds?: number
  environment?: {
    embedding_backend: string
    vector_backend: string
    llm: HealthResponse['llm']
  }
  standard_discovery?: EvalMetric
  clause_retrieval?: EvalMetric
  consumer_lookup?: EvalMetric
  consumer_description_search?: EvalMetric
  regulatory?: EvalMetric
  gap_analysis?: EvalMetric
  amendment_impact?: EvalMetric
  grounding?: EvalMetric
}
