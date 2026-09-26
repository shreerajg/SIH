import { useEffect, useState } from 'react'
import { CalendarClock, ExternalLink, Gavel, ShieldAlert, X } from 'lucide-react'
import { api, apiError } from '@/lib/api'
import type { RegulatoryDetail, RegulatoryEvidence } from '@/lib/types'
import { REGULATORY_META, formatDate } from '@/lib/format'
import { DemoDataBadge, ErrorState, RegulatoryBadge } from './primitives'

/**
 * Shows the stored records behind a regulatory status.
 *
 * A status word on its own is not useful for a compliance decision — the
 * notification number, the dates and the scheme are what a manufacturer acts
 * on, so they are always one click away.
 */
export function RegulatoryDrawer({
  standardId,
  onClose,
}: {
  standardId: string | null
  onClose: () => void
}) {
  const [detail, setDetail] = useState<RegulatoryDetail | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!standardId) return
    let cancelled = false
    setLoading(true)
    setError('')
    setDetail(null)
    api
      .standardRegulatory(standardId)
      .then((data) => !cancelled && setDetail(data))
      .catch((e) => !cancelled && setError(apiError(e)))
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }, [standardId])

  useEffect(() => {
    if (!standardId) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [standardId, onClose])

  if (!standardId) return null

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-ink-950/30 backdrop-blur-[2px]" onClick={onClose} aria-hidden />
      <aside className="relative flex h-full w-full max-w-lg flex-col bg-white shadow-panel animate-fade-up">
        <header className="flex items-start justify-between gap-4 border-b border-ink-200 px-6 py-4">
          <div>
            <div className="section-title">Regulatory evidence</div>
            <h2 className="mt-1 text-base font-bold text-ink-900">{standardId}</h2>
          </div>
          <button className="btn-ghost btn-sm" onClick={onClose} aria-label="Close">
            <X className="h-4 w-4" />
          </button>
        </header>

        <div className="scroll-thin flex-1 overflow-y-auto px-6 py-5">
          {loading && (
            <div className="space-y-3">
              <div className="skeleton h-5 w-1/3" />
              <div className="skeleton h-3 w-full" />
              <div className="skeleton h-3 w-4/5" />
            </div>
          )}

          {error && <ErrorState message={error} />}

          {detail && (
            <div className="space-y-5">
              <section className="card p-4">
                <RegulatoryBadge
                  status={detail.status.status}
                  verified={detail.status.verified}
                />
                <p className="mt-2.5 text-sm leading-relaxed text-ink-700">
                  {detail.status.message}
                </p>
              </section>

              {detail.history.length === 0 ? (
                <section className="card border-ink-200 bg-ink-50/60 p-4">
                  <div className="flex items-start gap-2.5">
                    <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-ink-400" />
                    <p className="text-sm leading-relaxed text-ink-600">
                      No Quality Control Order record is stored for this standard. The
                      platform reports this as <strong>unable to verify</strong> rather than
                      concluding the standard is voluntary.
                    </p>
                  </div>
                </section>
              ) : (
                <section>
                  <div className="section-title mb-2">
                    Stored records ({detail.history.length})
                  </div>
                  <ol className="space-y-3">
                    {detail.history.map((record, i) => (
                      <RecordCard key={`${record.notification_number}-${i}`} record={record} />
                    ))}
                  </ol>
                </section>
              )}

              <p className="rounded-xl bg-ink-50 px-3.5 py-3 text-xs leading-relaxed text-ink-500">
                {detail.note}
              </p>
            </div>
          )}
        </div>
      </aside>
    </div>
  )
}

function RecordCard({ record }: { record: RegulatoryEvidence }) {
  const meta =
    REGULATORY_META[record.effective_status as keyof typeof REGULATORY_META] ??
    REGULATORY_META.UNABLE_TO_VERIFY

  return (
    <li className="card p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className={`chip ${meta.chip}`}>
          <Gavel className="h-3.5 w-3.5" />
          {meta.label}
        </span>
        {record.is_demo && <DemoDataBadge compact />}
        {record.declared_status !== record.effective_status && (
          <span className="chip bg-ink-100 text-ink-500" title="How the record reads before dates are applied">
            declared {record.declared_status}
          </span>
        )}
      </div>

      {record.qco_name && (
        <h3 className="mt-2.5 text-sm font-semibold leading-snug text-ink-900">
          {record.qco_name}
        </h3>
      )}

      <dl className="mt-2.5 space-y-1.5 text-sm">
        <Row label="Notification" value={record.notification_number} />
        <Row label="Notified on" value={formatDate(record.notification_date)} />
        <Row
          label="Effective from"
          value={formatDate(record.effective_date)}
          icon={<CalendarClock className="h-3.5 w-3.5 text-ink-400" />}
        />
        <Row label="Scheme" value={record.scheme} />
        <Row label="Product" value={record.product_name} />
        <Row label="Issued by" value={record.ministry} />
      </dl>

      {record.source_url ? (
        <a
          className="link mt-2.5 inline-flex items-center gap-1 text-xs"
          href={record.source_url}
          target="_blank"
          rel="noreferrer"
        >
          <ExternalLink className="h-3 w-3" />
          Official notification
        </a>
      ) : (
        <p className="mt-2.5 text-xs text-ink-400">
          No official source URL — this record is part of the demonstration dataset.
        </p>
      )}
    </li>
  )
}

function Row({
  label,
  value,
  icon,
}: {
  label: string
  value?: string | null
  icon?: React.ReactNode
}) {
  if (!value || value === '—') return null
  return (
    <div className="flex items-baseline justify-between gap-4">
      <dt className="shrink-0 text-xs font-medium text-ink-500">{label}</dt>
      <dd className="inline-flex items-center gap-1.5 text-right font-medium text-ink-800">
        {icon}
        {value}
      </dd>
    </div>
  )
}
