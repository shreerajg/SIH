import axios, { AxiosError } from 'axios'
import type {
  ChatResponse,
  ComplianceResponse,
  ComplianceTwinResponse,
  ConsumerCategoriesResponse,
  ConsumerStandardResponse,
  DiscoverStandardsResponse,
  FindingsResponse,
  EvaluationResults,
  OcrScanResponse,
  EvidenceListResponse,
  HealthResponse,
  ProductAnalyzeResponse,
  ProductProfile,
  CentreSearchResponse,
  ConsumerHallmarkGuide,
  HuidDescription,
  JewellerHallmarkGuide,
  ProcessGuidance,
  ProductSchemeGuidance,
  RAGResponse,
  SchemeGuidance,
  SchemeInfo,
  SourceDetail,
  StandardDetail,
  StandardRequirementsResponse,
  StandardsGraphResponse,
  StandardSummary,
  TrustResponse,
  AmendmentImpact,
  RegulatoryDetail,
  UploadedEvidence,
} from './types'

const baseURL = import.meta.env.VITE_API_BASE_URL || '/api'

export const http = axios.create({ baseURL, timeout: 120_000 })

/** Turn an axios failure into a message a user can act on. */
export function apiError(error: unknown): string {
  const err = error as AxiosError<{ detail?: string | { msg?: string }[] }>
  if (err?.code === 'ECONNABORTED') {
    return 'The request timed out. The first search of a session can be slow while the embedding model loads — try again.'
  }
  if (err?.response) {
    const detail = err.response.data?.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail) && detail[0]?.msg) return String(detail[0].msg)
    if (err.response.status === 503) {
      return 'The backend cannot reach its database. Run scripts/setup_demo.py and restart the API.'
    }
    return `Request failed (HTTP ${err.response.status}).`
  }
  if (err?.request) {
    return 'Could not reach the backend API. Start it with: cd backend && uvicorn app.main:app --reload --port 8000'
  }
  return 'Something went wrong.'
}

export const api = {
  health: () => http.get<HealthResponse>('/health').then((r) => r.data),

  trust: () => http.get<TrustResponse>('/trust').then((r) => r.data),

  // --- BIS hallmarking -------------------------------------------------------
  hallmarkingConsumerGuide: (material = 'gold') =>
    http
      .get<ConsumerHallmarkGuide>('/hallmarking/consumer-guide', { params: { material } })
      .then((r) => r.data),

  hallmarkingJewellerGuide: () =>
    http.get<JewellerHallmarkGuide>('/hallmarking/jeweller-guide').then((r) => r.data),

  hallmarkingCentres: (params: { state?: string; city?: string; operative_only?: boolean } = {}) =>
    http
      .get<CentreSearchResponse>('/hallmarking/centres', {
        params: {
          state: params.state || undefined,
          city: params.city || undefined,
          operative_only: params.operative_only || undefined,
        },
      })
      .then((r) => r.data),

  describeHuid: (code: string) =>
    http.get<HuidDescription>('/hallmarking/huid/describe', { params: { code } }).then((r) => r.data),

  // --- BIS certification schemes -------------------------------------------
  listSchemes: () =>
    http.get<SchemeInfo[]>('/certification/schemes').then((r) => r.data),

  getScheme: (schemeId: string) =>
    http.get<SchemeInfo>(`/certification/schemes/${schemeId}`).then((r) => r.data),

  schemeForProduct: (productId: string) =>
    http
      .get<ProductSchemeGuidance>(`/products/${productId}/certification-scheme`)
      .then((r) => r.data),

  processForProduct: (productId: string) =>
    http
      .get<ProcessGuidance>(`/products/${productId}/certification-process`)
      .then((r) => r.data),

  processForStandard: (standardId: string) =>
    http
      .get<ProcessGuidance>(`/standards/${standardId}/certification-process`)
      .then((r) => r.data),

  schemeForStandard: (standardId: string) =>
    http
      .get<SchemeGuidance>(`/standards/${standardId}/certification-scheme`)
      .then((r) => r.data),

  evaluation: () =>
    http.get<EvaluationResults>('/evaluation').then((r) => r.data),

  analyzeProduct: (description: string, name?: string) =>
    http
      .post<ProductAnalyzeResponse>('/products/analyze', { description, name })
      .then((r) => r.data),

  getProduct: (id: string) =>
    http.get<ProductProfile>(`/products/${id}`).then((r) => r.data),

  answerInterview: (
    id: string,
    answers: { field: string; value: unknown }[],
    skipRemaining = false,
  ) =>
    http
      .post<ProductAnalyzeResponse>(`/products/${id}/interview`, {
        answers,
        skip_remaining: skipRemaining,
      })
      .then((r) => r.data),

  discoverStandards: (id: string) =>
    http
      .post<DiscoverStandardsResponse>(`/products/${id}/discover-standards`)
      .then((r) => r.data),

  getProductStandards: (id: string) =>
    http.get<DiscoverStandardsResponse>(`/products/${id}/standards`).then((r) => r.data),

  runCompliance: (
    id: string,
    payload: {
      attributes?: Record<string, unknown>
      evidence?: { evidence_type: string; name: string; value?: string; metadata?: Record<string, unknown> }[]
      standard_ids?: string[]
    },
  ) =>
    http
      .post<ComplianceResponse>(`/products/${id}/compliance/analyze`, payload)
      .then((r) => r.data),

  complianceTwin: (id: string) =>
    http.get<ComplianceTwinResponse>(`/products/${id}/compliance`).then((r) => r.data),

  ragQuery: (payload: {
    question: string
    standard_ids?: string[]
    product_id?: string
    conversation_id?: string | null
  }) => http.post<RAGResponse>('/rag/query', payload).then((r) => r.data),

  standardRegulatory: (id: string) =>
    http.get<RegulatoryDetail>(`/standards/${id}/regulatory`).then((r) => r.data),

  listStandards: (category?: string) =>
    http
      .get<StandardSummary[]>('/standards', { params: category ? { category } : undefined })
      .then((r) => r.data),

  standardsGraph: (params: { category?: string; focus?: string; regulatory?: boolean } = {}) =>
    http
      .get<StandardsGraphResponse>('/standards/graph', {
        params: {
          category: params.category || undefined,
          focus: params.focus || undefined,
          regulatory: params.regulatory === false ? false : undefined,
        },
      })
      .then((r) => r.data),

  getStandard: (id: string) =>
    http.get<StandardDetail>(`/standards/${id}`).then((r) => r.data),

  standardFindings: (id: string) =>
    http.get<FindingsResponse>(`/standards/${id}/findings`).then((r) => r.data),

  standardRequirements: (id: string) =>
    http.get<StandardRequirementsResponse>(`/standards/${id}/requirements`).then((r) => r.data),

  standardAmendments: (id: string) =>
    http.get<AmendmentImpact[]>(`/standards/${id}/amendments`).then((r) => r.data),

  getSource: (chunkId: string) =>
    http.get<SourceDetail>(`/sources/${encodeURIComponent(chunkId)}`).then((r) => r.data),

  consumerLookup: (query: string) =>
    http
      .post<ConsumerStandardResponse>('/consumer/lookup', { query })
      .then((r) => r.data),

  consumerCategories: () =>
    http.get<ConsumerCategoriesResponse>('/consumer/categories').then((r) => r.data),

  consumerScan: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return http.post<OcrScanResponse>('/consumer/scan', form).then((r) => r.data)
  },

  listEvidence: (productId: string) =>
    http
      .get<EvidenceListResponse>(`/products/${productId}/evidence`)
      .then((r) => r.data),

  uploadEvidence: (
    productId: string,
    file: File,
    category: string,
    name = '',
    onProgress?: (percent: number) => void,
  ) => {
    const form = new FormData()
    form.append('file', file)
    form.append('category', category)
    form.append('name', name)
    return http
      .post<UploadedEvidence>(`/products/${productId}/evidence/upload`, form, {
        onUploadProgress: (e) => {
          if (onProgress && e.total) onProgress(Math.round((e.loaded / e.total) * 100))
        },
      })
      .then((r) => r.data)
  },

  getEvidence: (productId: string, evidenceId: string) =>
    http
      .get<UploadedEvidence>(`/products/${productId}/evidence/${evidenceId}`)
      .then((r) => r.data),

  deleteEvidence: (productId: string, evidenceId: string) =>
    http.delete(`/products/${productId}/evidence/${evidenceId}`).then((r) => r.data),

  // --- Dynamic Chat (live BIS knowledge retrieval) -------------------------
  chatMessage: (payload: {
    message: string
    conversation_id?: string | null
    language?: string
  }) =>
    http.post<ChatResponse>('/chat/message', {
      message: payload.message,
      conversation_id: payload.conversation_id,
      language: payload.language || 'en',
    }).then((r) => r.data),

  chatHealth: () =>
    http.get<{
      search_provider_available: boolean
      cache_enabled: boolean
      retrieval_enabled: boolean
    }>('/chat/health').then((r) => r.data),
}
