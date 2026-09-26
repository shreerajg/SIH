import { useState } from 'react'
import { CheckCircle2, ChevronDown, CircleDashed, TerminalSquare, XCircle } from 'lucide-react'
import type { EvaluationResults } from '@/lib/types'
import { formatDate } from '@/lib/format'
import { EmptyState, SectionHeading, Stat } from '@/components/primitives'

type Tone = 'good' | 'warn' | 'bad'

type HeadlineField = { field: string; label: string; invert?: boolean }

type MetricConfig = {
  key: keyof EvaluationResults
  label: string
  description: string
  headline: HeadlineField[]
}

const METRICS: MetricConfig[] = [
  {
    key: 'standard_discovery',
    label: 'Standard discovery',
    description: 'Does the right standard surface for a plain-language product description?',
    headline: [
      { field: 'recall_at_1', label: 'Recall@1' },
      { field: 'recall_at_3', label: 'Recall@3' },
      { field: 'mrr', label: 'MRR' },
    ],
  },
  {
    key: 'clause_retrieval',
    label: 'Clause retrieval',
    description: 'Does asking a question surface the clause that actually answers it?',
    headline: [
      { field: 'recall_at_5', label: 'Recall@5' },
      { field: 'mrr', label: 'MRR' },
    ],
  },
  {
    key: 'consumer_lookup',
    label: 'Consumer lookup (by code)',
    description: 'Typing an IS/DEMO code, including correct not-found behaviour.',
    headline: [{ field: 'accuracy', label: 'Accuracy' }],
  },
  {
    key: 'consumer_description_search',
    label: 'Consumer lookup (by description)',
    description: 'Typing a plain product name instead of a code (Priority 11).',
    headline: [{ field: 'accuracy', label: 'Accuracy' }],
  },
  {
    key: 'regulatory',
    label: 'Regulatory status',
    description: 'MANDATORY / UPCOMING / UNABLE_TO_VERIFY read from structured QCO records.',
    headline: [{ field: 'accuracy', label: 'Accuracy' }],
  },
  {
    key: 'gap_analysis',
    label: 'Gap analyzer',
    description: 'Does the rule engine reach the same status for the same evidence, every time?',
    headline: [{ field: 'accuracy', label: 'Accuracy' }],
  },
  {
    key: 'amendment_impact',
    label: 'Amendment impact',
    description: "An amendment must map to exactly the requirements its clause backs.",
    headline: [{ field: 'accuracy', label: 'Accuracy' }],
  },
  {
    key: 'grounding',
    label: 'RAG grounding (Evidence Shield)',
    description: 'Every displayed claim must cite a chunk that was actually retrieved.',
    headline: [
      { field: 'citation_validity', label: 'Citation validity' },
      { field: 'unsupported_claim_rate', label: 'Unsupported rate', invert: true },
    ],
  },
]

function toneFor(value: unknown, invert = false): Tone {
  if (typeof value !== 'number') return 'warn'
  const v = invert ? 1 - value : value
  if (v >= 0.9) return 'good'
  if (v >= 0.7) return 'warn'
  return 'bad'
}

function pct(value: unknown): string {
  return typeof value === 'number' ? `${Math.round(value * 100)}%` : '—'
}

export function MeasuredAccuracy({ data }: { data: EvaluationResults }) {
  if (!data.available) {
    return (
      <section className="mt-10">
        <SectionHeading
          title="Measured accuracy"
          description="Real numbers against ground truth, not a claim of quality."
        />
        <EmptyState
          icon={<TerminalSquare className="h-5 w-5" />}
          title="No evaluation has been run yet"
          description={
            data.message ||
            'Run the evaluation script to measure retrieval, consumer lookup, gap analysis, amendment impact and RAG grounding against independently-assigned ground truth.'
          }
        />
      </section>
    )
  }

  return (
    <section className="mt-10">
      <SectionHeading
        title="Measured accuracy"
        description="Every number below is computed against ground truth assigned by reading the source documents, not by running the system - see the note in the dataset file."
      />

      <div className="mb-4 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink-500">
        {data.generated_at && <span>Last run {formatDate(data.generated_at)}</span>}
        {data.environment && (
          <span>
            {data.environment.embedding_backend} ·{' '}
            {data.environment.llm.available
              ? `LLM: ${data.environment.llm.provider}`
              : 'retrieval-only (no LLM configured)'}
          </span>
        )}
        {typeof data.duration_seconds === 'number' && <span>{data.duration_seconds}s to run</span>}
      </div>

      <div className="space-y-3">
        {METRICS.map((metric) => {
          const result = data[metric.key] as
            | (Record<string, unknown> & { cases?: number; details?: Record<string, unknown>[] })
            | undefined
          if (!result || !result.cases) return null
          return (
            <MetricCard key={String(metric.key)} config={metric} result={result} />
          )
        })}
      </div>
    </section>
  )
}

function MetricCard({
  config,
  result,
}: {
  config: MetricConfig
  result: Record<string, unknown> & { cases?: number; details?: Record<string, unknown>[] }
}) {
  const [open, setOpen] = useState(false)
  const details = Array.isArray(result.details) ? result.details : []

  return (
    <article className="card overflow-hidden">
      <div className="p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3 className="text-sm font-bold text-ink-900">{config.label}</h3>
            <p className="mt-0.5 max-w-md text-xs leading-relaxed text-ink-500">
              {config.description}
            </p>
          </div>
          <span className="chip bg-ink-100 text-ink-600">{String(result.cases)} cases</span>
        </div>

        <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
          {config.headline.map((h) => (
            <Stat
              key={h.field}
              label={h.label}
              value={pct(result[h.field])}
              tone={toneFor(result[h.field], h.invert)}
            />
          ))}
        </div>

        {details.length > 0 && (
          <button
            className="btn-ghost btn-sm mt-3"
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
          >
            <ChevronDown className={`h-3.5 w-3.5 transition-transform ${open ? 'rotate-180' : ''}`} />
            {open ? 'Hide' : 'Show'} the {details.length} individual case
            {details.length === 1 ? '' : 's'}
          </button>
        )}
      </div>

      {open && (
        <div className="scroll-thin max-h-72 overflow-y-auto border-t border-ink-200 bg-ink-50/60 px-4 py-3">
          <ul className="space-y-1.5">
            {details.map((row, i) => (
              <CaseRow key={String(row.id ?? i)} row={row} />
            ))}
          </ul>
        </div>
      )}
    </article>
  )
}

function CaseRow({ row }: { row: Record<string, unknown> }) {
  // Three states, not two: a case that only hit_at_3 (missed the stricter
  // Recall@1 bar) is a partial result, not a full pass - collapsing it to a
  // plain green check would quietly hide the exact imperfection the Recall@1
  // stat above is reporting.
  let state: 'pass' | 'partial' | 'fail' | 'unknown' = 'unknown'
  if (typeof row.correct === 'boolean') {
    state = row.correct ? 'pass' : 'fail'
  } else if (typeof row.hit_at_1 === 'boolean' || typeof row.hit_at_3 === 'boolean') {
    state = row.hit_at_1 ? 'pass' : row.hit_at_3 ? 'partial' : 'fail'
  }

  const summaryParts = Object.entries(row)
    .filter(([k]) => !['id', 'correct', 'hit_at_1', 'hit_at_3', 'mismatches', 'details'].includes(k))
    .filter(([, v]) => v !== null && typeof v !== 'object')
    .map(([k, v]) => `${k.replace(/_/g, ' ')}: ${String(v)}`)

  return (
    <li className="flex items-start gap-2 text-xs">
      {state === 'unknown' && (
        <span className="mt-0.5 h-3.5 w-3.5 shrink-0 rounded-full bg-ink-200" />
      )}
      {state === 'pass' && <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-500" />}
      {state === 'partial' && (
        <CircleDashed
          className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-500"
          aria-label="Only recalled within a looser rank cutoff"
        />
      )}
      {state === 'fail' && <XCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-rose-500" />}
      <span className="text-ink-600">
        <span className="font-mono font-semibold text-ink-800">{String(row.id ?? '')}</span>{' '}
        {summaryParts.join(' · ')}
        {state === 'partial' && (
          <span className="ml-1 text-amber-600">(recalled at @3, not @1)</span>
        )}
      </span>
    </li>
  )
}
