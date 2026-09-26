import { HelpCircle } from 'lucide-react'
import type { ReadinessSummary } from '@/lib/types'
import { CATEGORY_LABELS, STATUS_META, titleCase } from '@/lib/format'
import type { ComplianceStatus } from '@/lib/types'

const ORDER: ComplianceStatus[] = [
  'SUPPORTED',
  'POTENTIAL_GAP',
  'TEST_REQUIRED',
  'DOCUMENT_REQUIRED',
  'UNKNOWN',
  'OFFICIAL_VERIFICATION_REQUIRED',
  'NOT_APPLICABLE',
]

export function ReadinessMeter({ readiness }: { readiness: ReadinessSummary }) {
  const segments = ORDER.filter((s) => (readiness.by_status[s] ?? 0) > 0).map((s) => ({
    status: s,
    count: readiness.by_status[s] ?? 0,
  }))
  const total = segments.reduce((sum, s) => sum + s.count, 0) || 1

  return (
    <div className="card p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-1.5">
            <span className="section-title">{readiness.label}</span>
            <span className="group relative">
              <HelpCircle className="h-3.5 w-3.5 cursor-help text-ink-300" />
              <span className="pointer-events-none absolute left-1/2 top-6 z-20 w-72 -translate-x-1/2 rounded-xl bg-ink-900 px-3 py-2 text-xs leading-relaxed text-white opacity-0 shadow-panel transition-opacity group-hover:opacity-100">
                {readiness.tooltip}
              </span>
            </span>
          </div>
          <div className="mt-1 flex items-baseline gap-2">
            <span className="text-4xl font-extrabold tabular-nums tracking-tight text-ink-900">
              {readiness.percentage}%
            </span>
            <span className="text-sm text-ink-500">
              {readiness.supported} of {readiness.assessable} assessable requirements have
              supporting information
            </span>
          </div>
        </div>
        <p className="max-w-xs text-xs leading-relaxed text-ink-400">
          Not a BIS certification result. {readiness.total_requirements - readiness.assessable}{' '}
          requirement(s) were excluded as not applicable.
        </p>
      </div>

      <div className="mt-4 flex h-3 w-full overflow-hidden rounded-full bg-ink-100">
        {segments.map((s) => (
          <div
            key={s.status}
            className={STATUS_META[s.status].bar}
            style={{ width: `${(s.count / total) * 100}%` }}
            title={`${STATUS_META[s.status].label}: ${s.count}`}
          />
        ))}
      </div>

      <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5">
        {segments.map((s) => (
          <span key={s.status} className="inline-flex items-center gap-1.5 text-xs text-ink-600">
            <span className={`h-2 w-2 rounded-full ${STATUS_META[s.status].dot}`} />
            {STATUS_META[s.status].label}
            <span className="font-bold tabular-nums text-ink-900">{s.count}</span>
          </span>
        ))}
      </div>
    </div>
  )
}

export function CategoryBreakdown({ readiness }: { readiness: ReadinessSummary }) {
  const categories = Object.entries(readiness.by_category)
  if (categories.length === 0) return null

  return (
    <div className="card p-5">
      <div className="section-title mb-3">Requirements by category</div>
      <div className="space-y-3">
        {categories
          .sort((a, b) => a[0].localeCompare(b[0]))
          .map(([category, statuses]) => {
            const total = Object.values(statuses).reduce((s, n) => s + n, 0)
            return (
              <div key={category}>
                <div className="mb-1 flex items-baseline justify-between text-sm">
                  <span className="font-semibold text-ink-800">
                    {CATEGORY_LABELS[category] ?? titleCase(category)}
                  </span>
                  <span className="text-xs tabular-nums text-ink-500">{total}</span>
                </div>
                <div className="flex h-2 overflow-hidden rounded-full bg-ink-100">
                  {ORDER.filter((s) => (statuses[s] ?? 0) > 0).map((s) => (
                    <div
                      key={s}
                      className={STATUS_META[s].bar}
                      style={{ width: `${((statuses[s] ?? 0) / total) * 100}%` }}
                      title={`${STATUS_META[s].label}: ${statuses[s]}`}
                    />
                  ))}
                </div>
              </div>
            )
          })}
      </div>
    </div>
  )
}
