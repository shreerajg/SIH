import { Fragment, useMemo, useState } from 'react'
import { ArrowUpDown, CheckCircle2, Filter, Paperclip } from 'lucide-react'
import type { ComplianceStatus, RequirementResult } from '@/lib/types'
import { CATEGORY_LABELS, STATUS_META, titleCase } from '@/lib/format'
import { StatusBadge } from './primitives'
import { EvidenceCitation } from './EvidenceDrawer'

const STATUS_ORDER: ComplianceStatus[] = [
  'POTENTIAL_GAP',
  'TEST_REQUIRED',
  'DOCUMENT_REQUIRED',
  'UNKNOWN',
  'OFFICIAL_VERIFICATION_REQUIRED',
  'SUPPORTED',
  'NOT_APPLICABLE',
]

export function RequirementTable({
  results,
  onOpenSource,
}: {
  results: RequirementResult[]
  onOpenSource: (chunkId: string) => void
}) {
  const [statusFilter, setStatusFilter] = useState<ComplianceStatus | 'ALL'>('ALL')
  const [categoryFilter, setCategoryFilter] = useState<string>('ALL')
  const [expanded, setExpanded] = useState<string | null>(null)

  const categories = useMemo(
    () => Array.from(new Set(results.map((r) => r.category))).sort(),
    [results],
  )
  const statuses = useMemo(
    () => STATUS_ORDER.filter((s) => results.some((r) => r.status === s)),
    [results],
  )

  const filtered = useMemo(() => {
    const rows = results.filter(
      (r) =>
        (statusFilter === 'ALL' || r.status === statusFilter) &&
        (categoryFilter === 'ALL' || r.category === categoryFilter),
    )
    return rows.sort(
      (a, b) => STATUS_ORDER.indexOf(a.status) - STATUS_ORDER.indexOf(b.status) ||
        a.requirement_code.localeCompare(b.requirement_code),
    )
  }, [results, statusFilter, categoryFilter])

  if (results.length === 0) {
    return (
      <div className="card px-6 py-10 text-center text-sm text-ink-500">
        No requirements have been assessed yet.
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-ink-500">
          <Filter className="h-3.5 w-3.5" />
          Filter
        </span>
        <button
          className={`chip ${statusFilter === 'ALL' ? 'bg-ink-900 text-white' : 'bg-white text-ink-600 ring-1 ring-ink-200'}`}
          onClick={() => setStatusFilter('ALL')}
        >
          All ({results.length})
        </button>
        {statuses.map((s) => (
          <button
            key={s}
            className={`chip ${statusFilter === s ? 'bg-ink-900 text-white' : STATUS_META[s].chip}`}
            onClick={() => setStatusFilter(s)}
          >
            {STATUS_META[s].label} ({results.filter((r) => r.status === s).length})
          </button>
        ))}
        <select
          className="ml-auto rounded-lg border border-ink-200 bg-white px-2.5 py-1.5 text-xs font-semibold text-ink-700"
          value={categoryFilter}
          onChange={(e) => setCategoryFilter(e.target.value)}
        >
          <option value="ALL">All categories</option>
          {categories.map((c) => (
            <option key={c} value={c}>
              {CATEGORY_LABELS[c] ?? titleCase(c)}
            </option>
          ))}
        </select>
      </div>

      <div className="card overflow-hidden">
        <div className="scroll-thin overflow-x-auto">
          <table className="w-full min-w-[860px] text-left text-sm">
            <thead className="border-b border-ink-200 bg-ink-50/70">
              <tr className="text-xs font-semibold uppercase tracking-wide text-ink-500">
                <th className="px-4 py-3">Requirement</th>
                <th className="px-3 py-3 w-32">Category</th>
                <th className="px-3 py-3 w-44">
                  <span className="inline-flex items-center gap-1">
                    Status <ArrowUpDown className="h-3 w-3" />
                  </span>
                </th>
                <th className="px-3 py-3 w-48">Source</th>
                <th className="px-3 py-3 w-40">Evidence</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-100">
              {filtered.map((r) => (
                <Fragment key={r.requirement_id}>
                  <tr
                    className="cursor-pointer align-top transition-colors hover:bg-ink-50/60"
                    onClick={() => setExpanded(expanded === r.requirement_id ? null : r.requirement_id)}
                  >
                    <td className="px-4 py-3.5">
                      <div className="flex items-start gap-2">
                        <span className="mt-0.5 rounded bg-ink-100 px-1.5 py-0.5 font-mono text-[10px] font-bold text-ink-500">
                          {r.requirement_code}
                        </span>
                        <span className="leading-relaxed text-ink-800">{r.requirement_text}</span>
                      </div>
                    </td>
                    <td className="px-3 py-3.5">
                      <span className="chip bg-ink-100 text-ink-600">
                        {CATEGORY_LABELS[r.category] ?? titleCase(r.category)}
                      </span>
                    </td>
                    <td className="px-3 py-3.5">
                      <StatusBadge status={r.status} />
                    </td>
                    <td className="px-3 py-3.5" onClick={(e) => e.stopPropagation()}>
                      <EvidenceCitation citation={r.source} onOpen={onOpenSource} />
                    </td>
                    <td className="px-3 py-3.5 text-xs text-ink-500">
                      {r.matched_evidence ? (
                        <span className="inline-flex items-start gap-1.5 text-emerald-700">
                          <Paperclip className="mt-0.5 h-3 w-3 shrink-0" />
                          {r.matched_evidence}
                        </span>
                      ) : (
                        <span className="text-ink-400">None supplied</span>
                      )}
                    </td>
                  </tr>
                  {expanded === r.requirement_id && (
                    <tr className="bg-ink-50/80">
                      <td colSpan={5} className="px-4 py-4">
                        <div className="grid gap-4 md:grid-cols-2">
                          <div>
                            <div className="section-title mb-1.5">Why this status</div>
                            <p className="text-sm leading-relaxed text-ink-700">{r.reason}</p>
                            <p className="mt-2 text-xs text-ink-400">
                              Decided by {r.decided_by.replace(/_/g, ' ')} · severity {r.severity} ·
                              evidence type {r.evidence_type.replace(/_/g, ' ')}
                            </p>
                          </div>
                          <div>
                            <div className="section-title mb-1.5">Recommended action</div>
                            {r.recommended_action ? (
                              <p className="text-sm leading-relaxed text-ink-700">{r.recommended_action}</p>
                            ) : (
                              <p className="inline-flex items-center gap-1.5 text-sm text-emerald-700">
                                <CheckCircle2 className="h-4 w-4" />
                                No action outstanding for this requirement.
                              </p>
                            )}
                            <blockquote className="mt-3 rounded-lg border-l-2 border-ink-300 bg-white px-3 py-2 text-xs leading-relaxed text-ink-600">
                              {r.source.excerpt}
                            </blockquote>
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {filtered.length === 0 && (
        <div className="card px-6 py-8 text-center text-sm text-ink-500">
          No requirements match the current filters.
        </div>
      )}
    </div>
  )
}
