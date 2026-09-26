import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  ChevronDown,
  ClipboardCheck,
  FileCheck2,
  Gauge,
  Info,
  Loader2,
  Pencil,
  Play,
  Sparkles,
  UploadCloud,
} from 'lucide-react'
import { api, apiError } from '@/lib/api'
import type {
  ComplianceResponse,
  ComplianceStatus,
  ProductProfile,
  RequirementResult,
} from '@/lib/types'
import { formFor, groupEvidence, isAdvancedField, type AttributeField } from '@/lib/gapForm'
import { attributeLabel, STATUS_META } from '@/lib/format'
import { RequirementTable } from '@/components/RequirementTable'
import { ReadinessMeter, CategoryBreakdown } from '@/components/ComplianceSummary'
import { EvidenceCitation, EvidenceDrawer, useEvidenceDrawer } from '@/components/EvidenceDrawer'
import { EvidenceUpload } from '@/components/EvidenceUpload'
import {
  DisclaimerBanner,
  EmptyState,
  ErrorState,
  LoadingSteps,
  SectionHeading,
  StatusBadge,
} from '@/components/primitives'

const STEPS = [
  'Loading applicable standards…',
  'Extracting standard requirements…',
  'Matching your evidence to each requirement…',
  'Running pre-compliance analysis…',
]

/** Max important questions shown before the rest fold into advanced details. */
const MAX_IMPORTANT = 5

/** Priority order for the "what needs your attention" list. */
const ATTENTION_ORDER: ComplianceStatus[] = [
  'POTENTIAL_GAP',
  'TEST_REQUIRED',
  'DOCUMENT_REQUIRED',
  'OFFICIAL_VERIFICATION_REQUIRED',
  'UNKNOWN',
]

const SEVERITY_RANK: Record<string, number> = { high: 0, critical: 0, medium: 1, low: 2 }

/** The five outcome cards, in the order the spec asks for. */
const CARD_DEFS: { key: string; label: string; statuses: ComplianceStatus[] }[] = [
  { key: 'SUPPORTED', label: 'Supported', statuses: ['SUPPORTED'] },
  { key: 'TEST_REQUIRED', label: 'Tests required', statuses: ['TEST_REQUIRED'] },
  { key: 'DOCUMENT_REQUIRED', label: 'Documents required', statuses: ['DOCUMENT_REQUIRED'] },
  { key: 'UNKNOWN', label: 'Needs review', statuses: ['UNKNOWN', 'POTENTIAL_GAP'] },
  { key: 'OFFICIAL_VERIFICATION_REQUIRED', label: 'Official verification', statuses: ['OFFICIAL_VERIFICATION_REQUIRED'] },
]

const hasValue = (v?: string) => v !== undefined && v !== null && v !== ''
const displayKnown = (v: string) => (v === 'true' ? 'Yes' : v === 'false' ? 'No' : v)

export function GapAnalysis() {
  const { productId = '' } = useParams()
  const drawer = useEvidenceDrawer()
  const [product, setProduct] = useState<ProductProfile | null>(null)
  const [result, setResult] = useState<ComplianceResponse | null>(null)
  const [values, setValues] = useState<Record<string, string>>({})
  const [selectedEvidence, setSelectedEvidence] = useState<Set<string>>(new Set())
  const [uploadedCount, setUploadedCount] = useState(0)
  const [error, setError] = useState('')
  const [running, setRunning] = useState(false)
  const [step, setStep] = useState(0)
  const [editKnown, setEditKnown] = useState(false)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [openGroup, setOpenGroup] = useState<string | null>(null)
  const [showFull, setShowFull] = useState(false)
  const [showAllAttention, setShowAllAttention] = useState(false)

  const form = useMemo(() => formFor(product?.category ?? ''), [product?.category])
  const evidenceGroups = useMemo(() => groupEvidence(form.evidence), [form.evidence])

  const load = useCallback(() => {
    setError('')
    api
      .getProduct(productId)
      .then((p) => {
        setProduct(p)
        const seeded: Record<string, string> = {}
        Object.entries(p.attributes).forEach(([k, v]) => {
          if (v !== null && v !== undefined && v !== '') seeded[k] = String(v)
        })
        setValues(seeded)
      })
      .catch((e) => setError(apiError(e)))
    api
      .complianceTwin(productId)
      .then((twin) => {
        if (twin.analysis_available) {
          setResult({
            product_id: twin.product.id,
            product_name: twin.product.name,
            generated_at: twin.product.updated_at ?? null,
            standards: twin.standards.map((s) => s.standard),
            results: twin.results,
            readiness: twin.readiness,
            evidence_provided: twin.evidence,
            llm_used: false,
            disclaimer: twin.disclaimer,
          })
          setSelectedEvidence(new Set(twin.evidence.map((e) => e.name)))
        }
      })
      .catch(() => undefined)
  }, [productId])

  useEffect(load, [load])

  useEffect(() => {
    if (!running) return
    setStep(0)
    const timer = setInterval(() => setStep((s) => Math.min(s + 1, STEPS.length - 1)), 800)
    return () => clearInterval(timer)
  }, [running])

  const toggleEvidence = (name: string) => {
    setSelectedEvidence((prev) => {
      const next = new Set(prev)
      if (next.has(name)) next.delete(name)
      else next.add(name)
      return next
    })
  }

  const run = async () => {
    setRunning(true)
    setError('')
    try {
      const attributes: Record<string, unknown> = {}
      Object.entries(values).forEach(([k, v]) => {
        if (v !== '') attributes[k] = v
      })
      const evidence = form.evidence
        .filter((e) => selectedEvidence.has(e.name))
        .map((e) => ({ evidence_type: e.evidence_type, name: e.name, value: '', metadata: {} }))
      setResult(await api.runCompliance(productId, { attributes, evidence }))
      setShowAllAttention(false)
    } catch (e) {
      setError(apiError(e))
    } finally {
      setRunning(false)
    }
  }

  // ---- Derived form state -------------------------------------------------
  const knownEntries = useMemo(
    () => Object.entries(values).filter(([, v]) => hasValue(v)),
    [values],
  )
  const knownGapFields = useMemo(
    () => form.attributes.filter((f) => hasValue(values[f.key])),
    [form.attributes, values],
  )
  const importantUnknown = useMemo(
    () => form.attributes.filter((f) => !isAdvancedField(f.key) && !hasValue(values[f.key])).slice(0, MAX_IMPORTANT),
    [form.attributes, values],
  )
  const advancedFields = useMemo(
    () => form.attributes.filter((f) => isAdvancedField(f.key)),
    [form.attributes],
  )

  const evidenceCount = selectedEvidence.size + uploadedCount

  const setValue = (key: string, value: string) => setValues((v) => ({ ...v, [key]: value }))

  return (
    <div className="mx-auto max-w-6xl px-4 py-12 sm:px-6">
      <div className="flex items-center gap-2.5">
        <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand-50 text-brand-600">
          <Gauge className="h-4.5 w-4.5" />
        </span>
        <span className="section-title">Step 3 of 4 · Pre-compliance analysis</span>
      </div>

      <h1 className="mt-4 text-3xl font-extrabold tracking-tight text-ink-900">
        What can you evidence today?
      </h1>
      <p className="mt-2 max-w-3xl text-sm leading-relaxed text-ink-500">
        We reuse what you have already told us, ask only for the few details that still matter, and
        check each standard requirement against the evidence you hold. Nothing is assumed in your
        favour — anything unknown is reported honestly.
      </p>

      {error && (
        <div className="mt-6">
          <ErrorState message={error} onRetry={run} />
        </div>
      )}

      {product && (
        <div className="mt-8 space-y-6">
          {/* Sections 1 & 2 side by side */}
          <div className="grid items-start gap-6 lg:grid-cols-2">
            {/* SECTION 1 — What we already know */}
            <section className="card p-5">
              <SectionHeading
                title="What we already know"
                description="Reused from your earlier steps"
                action={
                  knownGapFields.length > 0 ? (
                    <button className="btn-ghost btn-sm" onClick={() => setEditKnown((v) => !v)}>
                      <Pencil className="h-3.5 w-3.5" />
                      {editKnown ? 'Done' : 'Update product details'}
                    </button>
                  ) : undefined
                }
              />
              {knownEntries.length === 0 ? (
                <p className="text-sm text-ink-500">
                  No product details have been captured yet. Add them in the earlier profile step,
                  or declare what you know on the right.
                </p>
              ) : editKnown ? (
                <div className="space-y-3.5">
                  {knownGapFields.map((field) => (
                    <FieldControl key={field.key} field={field} value={values[field.key] ?? ''} onChange={setValue} />
                  ))}
                  <p className="text-xs leading-relaxed text-ink-400">
                    Other details carried over from earlier steps stay as shown.
                  </p>
                </div>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {knownEntries.map(([key, v]) => (
                    <span
                      key={key}
                      className="inline-flex items-center gap-1.5 rounded-xl border border-ink-200 bg-ink-50/60 px-3 py-1.5 text-sm"
                    >
                      <span className="text-ink-500">{attributeLabel(key)}</span>
                      <span className="font-semibold text-ink-900">{displayKnown(v)}</span>
                    </span>
                  ))}
                </div>
              )}
            </section>

            {/* SECTION 2 — What we still need */}
            <section className="card p-5">
              <SectionHeading
                title="What we still need"
                description={
                  importantUnknown.length > 0
                    ? 'A few details that change the analysis'
                    : 'The important details are covered'
                }
              />
              {form.attributes.length === 0 ? (
                <p className="text-sm text-ink-500">
                  There is no structured declaration form for this product category yet, so the
                  analysis will run on your evidence alone.
                </p>
              ) : (
                <>
                  {importantUnknown.length === 0 ? (
                    <p className="rounded-xl bg-emerald-50 px-3.5 py-3 text-sm leading-relaxed text-emerald-800 ring-1 ring-emerald-100">
                      You have declared everything important we ask for. You can still add optional
                      technical details below.
                    </p>
                  ) : (
                    <div className="space-y-3.5">
                      {importantUnknown.map((field) => (
                        <FieldControl key={field.key} field={field} value={values[field.key] ?? ''} onChange={setValue} />
                      ))}
                    </div>
                  )}

                  {advancedFields.length > 0 && (
                    <div className="mt-4 border-t border-ink-100 pt-4">
                      <button
                        className="btn-ghost btn-sm"
                        onClick={() => setShowAdvanced((v) => !v)}
                        aria-expanded={showAdvanced}
                      >
                        <Sparkles className="h-3.5 w-3.5" />
                        {showAdvanced ? 'Hide technical details' : 'Show more technical details'}
                        <ChevronDown className={`h-3.5 w-3.5 transition-transform ${showAdvanced ? 'rotate-180' : ''}`} />
                      </button>
                      {showAdvanced && (
                        <div className="mt-3.5 space-y-3.5">
                          {advancedFields.map((field) => (
                            <FieldControl key={field.key} field={field} value={values[field.key] ?? ''} onChange={setValue} />
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </>
              )}
            </section>
          </div>

          {/* SECTION 3 — Evidence you have (full width) */}
          <section className="card p-5">
            <SectionHeading
              title="Evidence you have"
              description={`${selectedEvidence.size} checklist item${selectedEvidence.size === 1 ? '' : 's'} selected · ${uploadedCount} document${uploadedCount === 1 ? '' : 's'} uploaded`}
            />

            {evidenceGroups.length > 0 && (
              <div className="space-y-2">
                {evidenceGroups.map((group) => {
                  const selectedInGroup = group.items.filter((i) => selectedEvidence.has(i.name)).length
                  const isOpen = openGroup === group.key
                  return (
                    <div key={group.key} className="overflow-hidden rounded-xl border border-ink-200">
                      <button
                        type="button"
                        className="flex w-full items-center gap-3 px-3.5 py-3 text-left transition-colors hover:bg-ink-50/60"
                        onClick={() => setOpenGroup(isOpen ? null : group.key)}
                        aria-expanded={isOpen}
                      >
                        <span className="flex-1">
                          <span className="text-sm font-semibold text-ink-800">{group.label}</span>
                          <span className="block text-xs text-ink-400">{group.hint}</span>
                        </span>
                        {selectedInGroup > 0 && (
                          <span className="chip bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200">
                            {selectedInGroup} selected
                          </span>
                        )}
                        <ChevronDown className={`h-4 w-4 shrink-0 text-ink-400 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
                      </button>
                      {isOpen && (
                        <div className="space-y-1.5 border-t border-ink-100 bg-ink-50/30 px-3 py-3">
                          {group.items.map((item) => (
                            <label
                              key={item.name}
                              className={`flex cursor-pointer items-start gap-2.5 rounded-lg border px-3 py-2 text-sm transition-colors ${
                                selectedEvidence.has(item.name)
                                  ? 'border-emerald-300 bg-emerald-50'
                                  : 'border-ink-200 bg-white hover:bg-ink-50'
                              }`}
                            >
                              <input
                                type="checkbox"
                                className="mt-0.5 h-4 w-4 rounded border-ink-300 text-emerald-600 focus:ring-emerald-500"
                                checked={selectedEvidence.has(item.name)}
                                onChange={() => toggleEvidence(item.name)}
                              />
                              <span className="font-medium text-ink-800">{item.name}</span>
                            </label>
                          ))}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            )}

            <p className="mt-3 text-xs leading-relaxed text-ink-400">
              The platform records that evidence exists. It does not read or judge the evidence
              itself — that remains the job of a conformity assessment body.
            </p>

            <div className="mt-4 border-t border-ink-100 pt-4">
              <div className="mb-3 flex items-center gap-1.5 text-sm font-semibold text-ink-700">
                <UploadCloud className="h-4 w-4 text-brand-600" />
                Upload evidence
              </div>
              <EvidenceUpload
                productId={productId}
                onCountChange={setUploadedCount}
                onChange={() => {
                  if (result && !running) void run()
                }}
              />
            </div>
          </section>

          {/* Live summary + single CTA */}
          <div className="card flex flex-col items-center gap-4 p-5 sm:flex-row sm:justify-between">
            <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-sm">
              <Metric value={knownEntries.length} label="Known details" />
              <Metric value={importantUnknown.length} label="Missing important details" tone={importantUnknown.length > 0 ? 'warn' : 'ok'} />
              <Metric value={evidenceCount} label="Evidence supplied" />
            </div>
            <button className="btn-primary w-full py-3 text-base sm:w-auto" onClick={run} disabled={running}>
              {running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
              Run pre-compliance analysis
            </button>
          </div>

          {/* Results */}
          {running && <LoadingSteps steps={STEPS} active={step} />}

          {!running && !result && !error && (
            <EmptyState
              icon={<ClipboardCheck className="h-5 w-5" />}
              title="No analysis has been run yet"
              description="Tell us what you know above and run the analysis. Requirements without supporting information are reported honestly rather than skipped."
            />
          )}

          {result && !running && (
            <ResultView
              result={result}
              productId={productId}
              showFull={showFull}
              onToggleFull={() => setShowFull((v) => !v)}
              showAllAttention={showAllAttention}
              onToggleAttention={() => setShowAllAttention((v) => !v)}
              onOpenSource={drawer.open}
            />
          )}
        </div>
      )}

      <EvidenceDrawer chunkId={drawer.chunkId} onClose={drawer.close} onNavigate={drawer.open} />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Field control (actual value / Yes / No / Not known)
// ---------------------------------------------------------------------------

function FieldControl({
  field,
  value,
  onChange,
}: {
  field: AttributeField
  value: string
  onChange: (key: string, value: string) => void
}) {
  return (
    <div>
      <label className="label" htmlFor={field.key}>
        {field.label}
        {field.unit ? ` (${field.unit})` : ''}
      </label>
      {field.type === 'boolean' ? (
        <div className="flex gap-2">
          {[
            { label: 'Yes', val: 'Yes' },
            { label: 'No', val: 'No' },
            { label: 'Not sure', val: '' },
          ].map((opt) => {
            const active = opt.val === '' ? !hasValue(value) : value === opt.val
            return (
              <button
                key={opt.label}
                type="button"
                className={`flex-1 rounded-xl border px-3 py-2 text-sm font-semibold transition-colors ${
                  active
                    ? opt.val === ''
                      ? 'border-ink-300 bg-ink-100 text-ink-600'
                      : 'border-brand-500 bg-brand-600 text-white'
                    : 'border-ink-200 bg-white text-ink-600 hover:bg-ink-50'
                }`}
                onClick={() => onChange(field.key, opt.val)}
              >
                {opt.label}
              </button>
            )
          })}
        </div>
      ) : field.type === 'select' ? (
        <select
          id={field.key}
          className="field"
          value={value}
          onChange={(e) => onChange(field.key, e.target.value)}
        >
          <option value="">Not declared</option>
          {field.options?.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      ) : (
        <input
          id={field.key}
          className="field"
          type={field.type === 'number' ? 'number' : 'text'}
          step="any"
          value={value}
          onChange={(e) => onChange(field.key, e.target.value)}
          placeholder="Leave blank if not known"
        />
      )}
      {field.help && <p className="mt-1 text-xs text-ink-400">{field.help}</p>}
    </div>
  )
}

function Metric({ value, label, tone = 'default' }: { value: number; label: string; tone?: 'default' | 'warn' | 'ok' }) {
  const color = tone === 'warn' ? 'text-amber-600' : tone === 'ok' ? 'text-emerald-600' : 'text-ink-900'
  return (
    <span className="inline-flex items-baseline gap-1.5">
      <span className={`text-xl font-extrabold tabular-nums ${color}`}>{value}</span>
      <span className="text-ink-500">{label}</span>
    </span>
  )
}

// ---------------------------------------------------------------------------
// Result view
// ---------------------------------------------------------------------------

function ResultView({
  result,
  productId,
  showFull,
  onToggleFull,
  showAllAttention,
  onToggleAttention,
  onOpenSource,
}: {
  result: ComplianceResponse
  productId: string
  showFull: boolean
  onToggleFull: () => void
  showAllAttention: boolean
  onToggleAttention: () => void
  onOpenSource: (chunkId: string) => void
}) {
  const { readiness, results } = result

  const verifiedCount = useMemo(() => results.filter((r) => r.source.is_verified).length, [results])
  const allDemo = results.length > 0 && verifiedCount === 0
  const mixed = verifiedCount > 0 && verifiedCount < results.length

  const attention = useMemo(() => {
    return results
      .filter((r) => ATTENTION_ORDER.includes(r.status))
      .sort(
        (a, b) =>
          ATTENTION_ORDER.indexOf(a.status) - ATTENTION_ORDER.indexOf(b.status) ||
          (SEVERITY_RANK[a.severity?.toLowerCase()] ?? 1) - (SEVERITY_RANK[b.severity?.toLowerCase()] ?? 1) ||
          a.requirement_code.localeCompare(b.requirement_code),
      )
  }, [results])

  const shownAttention = showAllAttention ? attention : attention.slice(0, 6)

  return (
    <div className="space-y-5">
      {/* Provenance label */}
      {allDemo && <RequirementSetBadge tone="demo" />}
      {mixed && <RequirementSetBadge tone="mixed" verified={verifiedCount} total={results.length} />}

      <ReadinessMeter readiness={readiness} />

      {/* Five outcome cards */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {CARD_DEFS.map((card) => {
          const count = card.statuses.reduce((sum, s) => sum + (readiness.by_status[s] ?? 0), 0)
          const meta = STATUS_META[card.statuses[0]]
          return (
            <div key={card.key} className="card p-4">
              <div className="flex items-center gap-1.5">
                <span className={`h-2.5 w-2.5 rounded-full ${meta.dot}`} />
                <span className="text-2xl font-extrabold tabular-nums text-ink-900">{count}</span>
              </div>
              <div className="mt-1 text-xs font-semibold text-ink-600">{card.label}</div>
            </div>
          )
        })}
      </div>

      {/* What needs your attention */}
      {attention.length > 0 && (
        <section>
          <SectionHeading
            title="What needs your attention"
            description={`${attention.length} item${attention.length === 1 ? '' : 's'} ranked by priority`}
          />
          <div className="space-y-2.5">
            {shownAttention.map((r) => (
              <AttentionCard key={r.requirement_id} r={r} onOpenSource={onOpenSource} />
            ))}
          </div>
          {attention.length > 6 && (
            <button className="btn-ghost btn-sm mt-3" onClick={onToggleAttention}>
              <ChevronDown className={`h-3.5 w-3.5 transition-transform ${showAllAttention ? 'rotate-180' : ''}`} />
              {showAllAttention ? 'Show fewer' : `Show all ${attention.length} items`}
            </button>
          )}
        </section>
      )}

      {/* Full technical assessment (collapsed) */}
      <section>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <button className="btn-secondary btn-sm" onClick={onToggleFull} aria-expanded={showFull}>
            <FileCheck2 className="h-3.5 w-3.5" />
            {showFull ? 'Hide full technical assessment' : 'View full technical assessment'}
            <ChevronDown className={`h-3.5 w-3.5 transition-transform ${showFull ? 'rotate-180' : ''}`} />
          </button>
          <Link to={`/product/${productId}/compliance`} className="btn-ghost btn-sm">
            <FileCheck2 className="h-3.5 w-3.5" />
            Open Compliance Twin
          </Link>
        </div>
        {showFull && (
          <div className="mt-4 space-y-5">
            <CategoryBreakdown readiness={readiness} />
            <RequirementTable results={results} onOpenSource={onOpenSource} />
          </div>
        )}
      </section>

      <DisclaimerBanner text={result.disclaimer} compact />
    </div>
  )
}

function RequirementSetBadge({
  tone,
  verified,
  total,
}: {
  tone: 'demo' | 'mixed'
  verified?: number
  total?: number
}) {
  const tooltip =
    'Structured technical requirements in this prototype are based on the demo requirement set. Verified BIS Product Manuals and regulatory sources are shown separately and are not used as technical requirement records here.'
  return (
    <div className="flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-3.5 py-2.5 text-xs leading-relaxed text-amber-800">
      <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
      <span>
        <span className="font-bold">
          {tone === 'demo' ? 'Prototype requirement set' : `Mixed requirement set (${verified} of ${total} verified)`}
        </span>{' '}
        — {tooltip} This readiness score is a preparation indicator, not an official BIS
        determination.
      </span>
    </div>
  )
}

function AttentionCard({ r, onOpenSource }: { r: RequirementResult; onOpenSource: (chunkId: string) => void }) {
  return (
    <article className="card p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="flex items-start gap-2">
          <span className="mt-0.5 rounded bg-ink-100 px-1.5 py-0.5 font-mono text-[10px] font-bold text-ink-500">
            {r.requirement_code}
          </span>
          <span className="text-sm font-semibold leading-snug text-ink-900">{r.requirement_text}</span>
        </div>
        <StatusBadge status={r.status} />
      </div>
      <p className="mt-2 text-xs leading-relaxed text-ink-600">
        <span className="font-semibold text-ink-500">Why it matters: </span>
        {r.reason}
      </p>
      {r.recommended_action && (
        <p className="mt-1.5 text-xs leading-relaxed text-ink-600">
          <span className="font-semibold text-ink-500">What to do: </span>
          {r.recommended_action}
        </p>
      )}
      <div className="mt-2.5 flex flex-wrap items-center gap-2">
        <EvidenceCitation citation={r.source} onOpen={onOpenSource} />
        {r.matched_evidence && (
          <span className="text-xs text-emerald-700">Matched: {r.matched_evidence}</span>
        )}
      </div>
    </article>
  )
}
