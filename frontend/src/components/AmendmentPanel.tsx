import { ArrowRight, CalendarClock, GitCompareArrows, Target } from 'lucide-react'
import type { AmendmentImpact } from '@/lib/types'
import { AMENDMENT_RELEVANCE_META, formatDate } from '@/lib/format'
import { DemoDataBadge } from './primitives'

export function AmendmentPanel({ impacts }: { impacts: AmendmentImpact[] }) {
  if (impacts.length === 0) {
    return (
      <div className="card px-6 py-10 text-center">
        <p className="text-sm text-ink-500">
          No amendments are recorded for the standards matched to this product.
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {impacts.map((impact) => {
        const a = impact.amendment
        return (
          <article key={a.id} className="card overflow-hidden">
            <header className="flex flex-wrap items-start justify-between gap-3 border-b border-ink-200 bg-amber-50/50 px-5 py-4">
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded-lg bg-ink-900 px-2 py-1 font-mono text-xs font-bold text-white">
                    {a.display_number}
                  </span>
                  <span className="chip bg-amber-100 text-amber-800 ring-1 ring-amber-200">
                    {a.amendment_number}
                  </span>
                  <span className="chip bg-white text-ink-600 ring-1 ring-ink-200">
                    Clause {a.affected_clause}
                  </span>
                  {a.is_mock && <DemoDataBadge compact />}
                </div>
                <p className="mt-2 text-sm font-medium leading-relaxed text-ink-800">{a.summary}</p>
              </div>
              <div className="text-right text-xs text-ink-500">
                <div className="inline-flex items-center gap-1.5">
                  <CalendarClock className="h-3.5 w-3.5" />
                  Effective {formatDate(a.effective_date)}
                </div>
                <div className="mt-0.5">Published {formatDate(a.publication_date)}</div>
              </div>
            </header>

            <div className="px-5 py-4">
              {impact.changed_numbers.length > 0 && (
                <div className="mb-4 flex flex-wrap gap-2">
                  {impact.changed_numbers.map((change, i) => (
                    <span
                      key={i}
                      className={`chip ring-1 ${
                        change.direction === 'tightened'
                          ? 'bg-rose-50 text-rose-700 ring-rose-200'
                          : change.direction === 'relaxed'
                            ? 'bg-emerald-50 text-emerald-700 ring-emerald-200'
                            : 'bg-ink-100 text-ink-600 ring-ink-200'
                      }`}
                    >
                      {change.old ?? '—'} {change.unit}
                      <ArrowRight className="h-3 w-3" />
                      {change.new ?? '—'} {change.unit}
                      <span className="ml-0.5 text-[10px] uppercase opacity-70">{change.direction}</span>
                    </span>
                  ))}
                </div>
              )}

              <div className="section-title mb-2 flex items-center gap-1.5">
                <GitCompareArrows className="h-3.5 w-3.5" />
                Clause text difference (computed, not generated)
              </div>
              <p className="rounded-xl border border-ink-200 bg-white px-4 py-3 text-sm leading-relaxed">
                {impact.diff.map((seg, i) => {
                  if (seg.op === 'equal') return <span key={i} className="text-ink-600">{seg.text}</span>
                  if (seg.op === 'delete')
                    return (
                      <span key={i} className="rounded bg-rose-100 text-rose-800 line-through decoration-rose-400">
                        {seg.text}
                      </span>
                    )
                  return (
                    <span key={i} className="rounded bg-emerald-100 font-medium text-emerald-800">
                      {seg.text}
                    </span>
                  )
                })}
              </p>

              {impact.product_impact && (
                <div className="mt-4 rounded-xl border border-ink-200 bg-white px-4 py-3">
                  <div className="mb-1.5 flex flex-wrap items-center gap-2">
                    <span className="section-title">Relevance to this product</span>
                    <span
                      className={`chip ${AMENDMENT_RELEVANCE_META[impact.product_impact.relevance].chip}`}
                      title={AMENDMENT_RELEVANCE_META[impact.product_impact.relevance].description}
                    >
                      <Target className="h-3 w-3" />
                      {AMENDMENT_RELEVANCE_META[impact.product_impact.relevance].label}
                    </span>
                  </div>
                  <p className="text-sm leading-relaxed text-ink-700">
                    {impact.product_impact.reason}
                  </p>
                  {impact.product_impact.supported_requirement_codes.length > 0 && (
                    <p className="mt-2 text-xs leading-relaxed text-ink-500">
                      Already reported as supported:{' '}
                      <span className="font-semibold text-ink-700">
                        {impact.product_impact.supported_requirement_codes.join(', ')}
                      </span>{' '}
                      — that evidence was produced against the previous wording.
                    </p>
                  )}
                </div>
              )}

              <div className="mt-4 rounded-xl border border-brand-200 bg-brand-50/50 px-4 py-3">
                <div className="section-title mb-1 text-brand-700">Potential impact</div>
                <p className="text-sm leading-relaxed text-ink-800">{impact.potential_impact}</p>
                <p className="mt-2 text-xs text-ink-500">
                  Source: {impact.impact_source === 'llm' ? 'language model summary of the computed diff' : 'computed from the stored clause wordings'}
                  {impact.affected_requirements.length > 0 && (
                    <> · Affects requirement(s): {impact.affected_requirements.join(', ')}</>
                  )}
                </p>
              </div>
            </div>
          </article>
        )
      })}
    </div>
  )
}
