import type {
  AmendmentRelevance,
  ComplianceStatus,
  Relevance,
  RegulatoryStatusValue,
} from './types'

/** Consistent colour semantics across the whole app. */
export const STATUS_META: Record<
  ComplianceStatus,
  { label: string; chip: string; dot: string; bar: string; description: string }
> = {
  SUPPORTED: {
    label: 'Supported',
    chip: 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200',
    dot: 'bg-emerald-500',
    bar: 'bg-emerald-500',
    description: 'Supporting information for this requirement is on file.',
  },
  POTENTIAL_GAP: {
    label: 'Potential gap',
    chip: 'bg-rose-50 text-rose-700 ring-1 ring-rose-200',
    dot: 'bg-rose-500',
    bar: 'bg-rose-500',
    description: 'A declared value appears to conflict with the clause limit.',
  },
  TEST_REQUIRED: {
    label: 'Test required',
    chip: 'bg-amber-50 text-amber-700 ring-1 ring-amber-200',
    dot: 'bg-amber-500',
    bar: 'bg-amber-500',
    description: 'No test report covering this requirement was supplied.',
  },
  DOCUMENT_REQUIRED: {
    label: 'Document required',
    chip: 'bg-orange-50 text-orange-700 ring-1 ring-orange-200',
    dot: 'bg-orange-500',
    bar: 'bg-orange-500',
    description: 'A document or certificate is needed for this requirement.',
  },
  UNKNOWN: {
    label: 'Unknown',
    chip: 'bg-ink-100 text-ink-600 ring-1 ring-ink-200',
    dot: 'bg-ink-400',
    bar: 'bg-ink-400',
    description: 'Not enough information has been declared to assess this.',
  },
  NOT_APPLICABLE: {
    label: 'Not applicable',
    chip: 'bg-ink-50 text-ink-500 ring-1 ring-ink-200',
    dot: 'bg-ink-300',
    bar: 'bg-ink-300',
    description: 'This requirement is conditional and does not apply here.',
  },
  OFFICIAL_VERIFICATION_REQUIRED: {
    label: 'Official verification',
    chip: 'bg-violet-50 text-violet-700 ring-1 ring-violet-200',
    dot: 'bg-violet-500',
    bar: 'bg-violet-500',
    description: 'Only the certifying authority can settle this requirement.',
  },
}

export const RELEVANCE_META: Record<Relevance, { label: string; chip: string; description: string }> = {
  HIGH: {
    label: 'High relevance',
    chip: 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200',
    description: 'Strong direct applicability evidence for this product was found in the source text.',
  },
  MEDIUM: {
    label: 'Medium relevance',
    chip: 'bg-brand-50 text-brand-700 ring-1 ring-brand-200',
    description: 'Some applicability evidence was found, but not a strong direct match.',
  },
  LOW: {
    label: 'Low relevance',
    chip: 'bg-ink-100 text-ink-600 ring-1 ring-ink-200',
    description: 'A weak retrieval candidate — little direct applicability evidence.',
  },
  NEEDS_VERIFICATION: {
    label: 'Needs review',
    chip: 'bg-amber-50 text-amber-700 ring-1 ring-amber-200',
    description:
      'Retrieved as potentially relevant, but strong direct applicability evidence was not found in the current source text.',
  },
}

export const REGULATORY_META: Record<
  RegulatoryStatusValue,
  { label: string; chip: string }
> = {
  MANDATORY: { label: 'Mandatory', chip: 'bg-rose-50 text-rose-700 ring-1 ring-rose-200' },
  UPCOMING: { label: 'Upcoming', chip: 'bg-amber-50 text-amber-700 ring-1 ring-amber-200' },
  WITHDRAWN: { label: 'Withdrawn', chip: 'bg-ink-100 text-ink-500 ring-1 ring-ink-200' },
  VOLUNTARY: { label: 'Voluntary', chip: 'bg-brand-50 text-brand-700 ring-1 ring-brand-200' },
  UNABLE_TO_VERIFY: {
    label: 'Unable to verify',
    chip: 'bg-ink-100 text-ink-600 ring-1 ring-ink-200',
  },
}

export const CORPUS_MODE_META: Record<
  'DEMO' | 'VERIFIED' | 'MIXED',
  { label: string; chip: string }
> = {
  DEMO: { label: 'Demo Corpus', chip: 'bg-saffron-50 text-saffron-800 ring-1 ring-saffron-200' },
  VERIFIED: { label: 'Verified Corpus', chip: 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200' },
  MIXED: { label: 'Mixed Corpus', chip: 'bg-brand-50 text-brand-700 ring-1 ring-brand-200' },
}

export const AMENDMENT_RELEVANCE_META: Record<
  AmendmentRelevance,
  { label: string; chip: string; description: string }
> = {
  LIKELY_RELEVANT: {
    label: 'Likely relevant',
    chip: 'bg-amber-50 text-amber-800 ring-1 ring-amber-200',
    description: 'The amended clause backs a requirement this product is assessed against.',
  },
  REQUIRES_REVIEW: {
    label: 'Requires review',
    chip: 'bg-brand-50 text-brand-700 ring-1 ring-brand-200',
    description: 'The standard applies, but the clause maps to no structured requirement.',
  },
  NO_DIRECT_MATCH_FOUND: {
    label: 'No direct match',
    chip: 'bg-ink-100 text-ink-600 ring-1 ring-ink-200',
    description: 'This standard is not among the ones matched to the product.',
  },
  UNABLE_TO_VERIFY: {
    label: 'Unable to verify',
    chip: 'bg-ink-100 text-ink-500 ring-1 ring-ink-200',
    description: 'Not enough context to assess relevance to this product.',
  },
}

export const CATEGORY_LABELS: Record<string, string> = {
  safety: 'Safety',
  testing: 'Testing',
  marking: 'Marking',
  material: 'Material',
  performance: 'Performance',
  construction: 'Construction',
  documentation: 'Documentation',
}

export function titleCase(value: string): string {
  return value
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
    .trim()
}

export function attributeLabel(key: string): string {
  const units: Record<string, string> = {
    capacity_litres: 'Capacity (L)',
    voltage_v: 'Voltage (V)',
    power_w: 'Power (W)',
    mass_kg: 'Mass (kg)',
    operating_pressure_kpa: 'Operating pressure (kPa)',
    working_pressure_kpa: 'Working pressure (kPa)',
    age_group_min_months: 'Minimum age (months)',
    max_water_temperature_c: 'Max water temperature (°C)',
    earth_continuity_ohm: 'Earth continuity (Ω)',
    insulation_resistance_mohm: 'Insulation resistance (MΩ)',
    supply_cord_csa_mm2: 'Supply cord CSA (mm²)',
    body_thickness_mm: 'Body thickness (mm)',
    base_thickness_mm: 'Base thickness (mm)',
    cord_length_mm: 'Cord length (mm)',
    liner_density_kg_m3: 'Liner density (kg/m³)',
    peripheral_vision_deg: 'Peripheral vision (°)',
    visor_transmittance_percent: 'Visor transmittance (%)',
  }
  return units[key] ?? titleCase(key)
}

export function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  if (typeof value === 'number') return Number.isInteger(value) ? String(value) : value.toFixed(2)
  return String(value)
}

export function citationLabel(c: {
  display_number: string
  clause_number: string
  page_number: number | null
}): string {
  const parts = [c.display_number, `Clause ${c.clause_number}`]
  if (c.page_number && c.page_number > 0) parts.push(`Page ${c.page_number}`)
  return parts.join(' · ')
}

/**
 * How a source document is labelled in citations.
 *
 * The corpus holds BIS Product Manuals, Quality Control Orders and gazette
 * notifications alongside standards. None of the former is the full text of an
 * Indian Standard, so a citation that does not name the document kind lets
 * Product Manual text be read as Standard clause text.
 */
export const DOCUMENT_TYPE_META: Record<
  string,
  { label: string; short: string; chip: string; description: string }
> = {
  standard: {
    label: 'Indian Standard',
    short: 'Standard',
    chip: 'bg-brand-50 text-brand-700 ring-1 ring-brand-200',
    description: 'Text from the Indian Standard itself.',
  },
  product_manual: {
    label: 'BIS Product Manual',
    short: 'Product Manual',
    chip: 'bg-violet-50 text-violet-700 ring-1 ring-violet-200',
    description:
      'Official BIS certification guidance for this standard — sampling, testing and marking. Not the full text of the Indian Standard.',
  },
  qco: {
    label: 'Quality Control Order',
    short: 'QCO',
    chip: 'bg-rose-50 text-rose-700 ring-1 ring-rose-200',
    description:
      'A Government of India Quality Control Order (gazette notification). It makes a standard mandatory; it is not the standard.',
  },
  amendment: {
    label: 'Amendment',
    short: 'Amendment',
    chip: 'bg-amber-50 text-amber-700 ring-1 ring-amber-200',
    description: 'An amendment to a standard — it changes part of it, and is not the whole.',
  },
  gazette: {
    label: 'Gazette notification',
    short: 'Gazette',
    chip: 'bg-rose-50 text-rose-700 ring-1 ring-rose-200',
    description: 'A notification published in the Gazette of India.',
  },
  regulatory: {
    label: 'Regulatory document',
    short: 'Regulatory',
    chip: 'bg-orange-50 text-orange-700 ring-1 ring-orange-200',
    description: 'An official regulatory document or index.',
  },
  scheme_of_inspection_and_testing: {
    label: 'Scheme of Inspection and Testing',
    short: 'SIT',
    chip: 'bg-teal-50 text-teal-700 ring-1 ring-teal-200',
    description: 'The inspection and testing scheme attached to a certification.',
  },
  other: {
    label: 'Supporting document',
    short: 'Document',
    chip: 'bg-ink-100 text-ink-600 ring-1 ring-ink-200',
    description: 'A supporting document.',
  },
}

export function documentTypeMeta(value?: string | null) {
  return DOCUMENT_TYPE_META[value || 'standard'] ?? DOCUMENT_TYPE_META.other
}

export function formatBytes(bytes: number): string {
  if (!bytes || bytes < 0) return '0 B'
  if (bytes < 1024) return `${bytes} B`
  const kb = bytes / 1024
  if (kb < 1024) return `${kb.toFixed(kb < 10 ? 1 : 0)} KB`
  return `${(kb / 1024).toFixed(1)} MB`
}

export const UPLOAD_CATEGORY_LABELS: Record<string, string> = {
  datasheet: 'Datasheet',
  test_report: 'Test report',
  product_label: 'Product label / marking',
  technical_document: 'Technical document',
  certificate: 'Certificate',
  other: 'Other',
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value
  return d.toLocaleDateString('en-IN', { year: 'numeric', month: 'short', day: 'numeric' })
}
