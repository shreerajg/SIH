import { useEffect, useState } from 'react'
import {
  CheckCircle2,
  ChevronDown,
  FileCheck,
  Gavel,
  ShieldAlert,
  ShieldCheck,
} from 'lucide-react'
import { api, apiError } from '@/lib/api'
import type { EvaluationResults, TrustResponse } from '@/lib/types'
import { DisclaimerBanner, ErrorState, LoadingSkeleton, SectionHeading, Stat } from '@/components/primitives'
import { MeasuredAccuracy } from '@/components/MeasuredAccuracy'

/** The compact, judge-facing headline metrics — a small dynamic slice of the
 *  full evaluation, never hardcoded. The rest stays behind the technical link. */
const HEADLINE_METRICS: {
  key: keyof EvaluationResults
  label: string
  fields: { field: string; label: string }[]
}[] = [
  {
    key: 'standard_discovery',
    label: 'Standard discovery',
    fields: [
      { field: 'recall_at_1', label: 'Recall@1' },
      { field: 'recall_at_3', label: 'Recall@3' },
    ],
  },
  {
    key: 'clause_retrieval',
    label: 'Clause retrieval',
    fields: [{ field: 'recall_at_5', label: 'Recall@5' }],
  },
  {
    key: 'consumer_lookup',
    label: 'Consumer code lookup',
    fields: [{ field: 'accuracy', label: 'Accuracy' }],
  },
]

function pct(value: unknown): string {
  return typeof value === 'number' ? `${Math.round(value * 100)}%` : '—'
}

/** Maps the backend's named controls (which carry an "enforced_in" file path
 *  that stays internal) onto the short safeguard labels judges care about. */
function safeguardLabel(name: string): string | null {
  const labels: Record<string, string> = {
    'Closed status vocabulary': 'Rule-based gap analysis',
    'Deterministic amendment diff': 'Deterministic amendment comparison',
    'Provenance on every record': 'Provenance stored on every record',
  }
  return labels[name] ?? null
}

export function Trust() {
  const [data, setData] = useState<TrustResponse | null>(null)
  const [evaluation, setEvaluation] = useState<EvaluationResults | null>(null)
  const [error, setError] = useState('')
  const [showTechnical, setShowTechnical] = useState(false)

  useEffect(() => {
    api
      .trust()
      .then(setData)
      .catch((e) => setError(apiError(e)))
    api
      .evaluation()
      .then(setEvaluation)
      .catch(() => setEvaluation({ available: false }))
  }, [])

  if (error) {
    return (
      <div className="mx-auto max-w-4xl px-4 py-12 sm:px-6">
        <ErrorState message={error} />
      </div>
    )
  }
  if (!data) {
    return (
      <div className="mx-auto max-w-4xl px-4 py-12 sm:px-6">
        <LoadingSkeleton rows={3} />
      </div>
    )
  }

  const safeguards = data.controls
    .map((c) => safeguardLabel(c.name))
    .filter((s): s is string => !!s)

  const headline = HEADLINE_METRICS.map((m) => ({
    ...m,
    result: evaluation?.[m.key] as (Record<string, unknown> & { cases?: number }) | undefined,
  })).filter((m) => m.result && m.result.cases)

  return (
    <div className="mx-auto max-w-4xl px-4 py-12 sm:px-6">
      <div className="flex items-center gap-2.5">
        <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-emerald-50 text-emerald-600">
          <ShieldCheck className="h-4.5 w-4.5" />
        </span>
        <span className="section-title">Trust &amp; Provenance</span>
      </div>

      <h1 className="mt-4 text-3xl font-extrabold tracking-tight text-ink-900 sm:text-4xl">
        How we keep answers trustworthy
      </h1>
      <p className="mt-3 max-w-2xl text-base leading-relaxed text-ink-600">
        The platform uses verified sources, clause-level evidence and backend validation so
        unsupported claims are not presented as facts.
      </p>

      {/* Four primary trust cards */}
      <section className="mt-8 grid gap-4 sm:grid-cols-2">
        <TrustCard
          icon={<ShieldCheck className="h-4.5 w-4.5" />}
          tone="emerald"
          title="Verified official sources"
          description="Official BIS Product Manuals and regulatory records are kept separate from synthetic demo data and clearly identified by source type."
          footnote={`${data.dataset.verified} of ${data.dataset.standards} documents are verified official sources`}
        />
        <TrustCard
          icon={<ShieldCheck className="h-4.5 w-4.5" />}
          tone="brand"
          title="Evidence Shield"
          description="Every generated claim must cite source evidence that was actually retrieved. Unsupported claims are removed; if nothing valid remains, the system abstains."
          footnote="Clause-level source evidence available"
        />
        <TrustCard
          icon={<FileCheck className="h-4.5 w-4.5" />}
          tone="violet"
          title="No invented standard IDs"
          description="If the model returns a standard ID that was not in the retrieved candidate list, the backend rejects it before display."
        />
        <TrustCard
          icon={<Gavel className="h-4.5 w-4.5" />}
          tone="rose"
          title="Regulatory status from official records"
          description="Mandatory, upcoming, withdrawn, voluntary, or unable-to-verify status comes only from structured QCO/regulatory records — never from model guessing."
          footnote={`${data.dataset.standards_with_regulatory_record} of ${data.dataset.standards} standards have a regulatory record on file`}
        />
      </section>

      {/* Additional safeguards */}
      {safeguards.length > 0 && (
        <section className="mt-6">
          <div className="card p-4">
            <div className="section-title mb-2.5">Additional safeguards</div>
            <ul className="grid gap-2 sm:grid-cols-3">
              {safeguards.map((s) => (
                <li key={s} className="flex items-start gap-2 text-sm text-ink-700">
                  <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-500" />
                  {s}
                </li>
              ))}
            </ul>
          </div>
        </section>
      )}

      {/* Measured prototype performance */}
      {evaluation?.available && headline.length > 0 && (
        <section className="mt-10">
          <SectionHeading
            title="Measured prototype performance"
            description="Evaluated against manually defined test cases for retrieval and lookup."
          />
          <div className="grid gap-3 sm:grid-cols-3">
            {headline.map((m) => (
              <div key={String(m.key)} className="card p-4">
                <div className="text-sm font-bold text-ink-900">{m.label}</div>
                <div className="mt-2 flex flex-wrap gap-3">
                  {m.fields.map((f) => (
                    <Stat key={f.field} label={f.label} value={pct(m.result?.[f.field])} tone="good" />
                  ))}
                </div>
              </div>
            ))}
          </div>

          <button
            className="btn-ghost btn-sm mt-3"
            onClick={() => setShowTechnical((v) => !v)}
            aria-expanded={showTechnical}
          >
            <ChevronDown className={`h-3.5 w-3.5 transition-transform ${showTechnical ? 'rotate-180' : ''}`} />
            {showTechnical ? 'Hide' : 'View'} technical evaluation details
          </button>

          {showTechnical && <MeasuredAccuracy data={evaluation} />}
        </section>
      )}

      {!evaluation?.available && (
        <section className="mt-10">
          <div className="card flex items-start gap-3 p-4">
            <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-ink-400" />
            <p className="text-sm leading-relaxed text-ink-500">
              {evaluation?.message ||
                'No evaluation has been run yet. Run the evaluation script to measure retrieval and lookup against ground truth.'}
            </p>
          </div>
        </section>
      )}

      <div className="mt-10">
        <DisclaimerBanner text={data.disclaimer} compact />
      </div>
    </div>
  )
}

const TONE_STYLES: Record<string, { bg: string; text: string }> = {
  emerald: { bg: 'bg-emerald-50', text: 'text-emerald-600' },
  brand: { bg: 'bg-brand-50', text: 'text-brand-600' },
  violet: { bg: 'bg-violet-50', text: 'text-violet-600' },
  rose: { bg: 'bg-rose-50', text: 'text-rose-600' },
}

function TrustCard({
  icon,
  tone,
  title,
  description,
  footnote,
}: {
  icon: React.ReactNode
  tone: keyof typeof TONE_STYLES
  title: string
  description: string
  footnote?: string
}) {
  const t = TONE_STYLES[tone]
  return (
    <article className="card p-5">
      <span className={`flex h-9 w-9 items-center justify-center rounded-xl ${t.bg} ${t.text}`}>
        {icon}
      </span>
      <h3 className="mt-3 text-sm font-bold text-ink-900">{title}</h3>
      <p className="mt-1.5 text-sm leading-relaxed text-ink-600">{description}</p>
      {footnote && <p className="mt-2 text-xs font-medium text-ink-400">{footnote}</p>}
    </article>
  )
}
