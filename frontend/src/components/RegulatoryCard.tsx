import { Gavel, ShieldAlert, ShieldCheck } from 'lucide-react'
import type { RegulatoryStatusInfo } from '@/lib/types'
import { REGULATORY_META, formatDate } from '@/lib/format'

/**
 * A compact regulatory-status summary. Reused wherever a standard's
 * mandatory/voluntary status needs a plain-English card rather than the raw
 * badge — the discovery results and the standard detail page both need this.
 *
 * Absence of a QCO record must read as "unable to verify", never "voluntary" —
 * that distinction is enforced by the backend and only rendered here.
 */
export function RegulatoryCard({
  regulatory,
  standardId,
  onView,
}: {
  regulatory: RegulatoryStatusInfo | null
  standardId: string | null
  onView: (id: string) => void
}) {
  const status = regulatory?.status ?? 'UNABLE_TO_VERIFY'
  const meta = REGULATORY_META[status]
  const unable = status === 'UNABLE_TO_VERIFY'

  return (
    <div className="card p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className={`chip ${meta.chip}`}>
              {unable ? <ShieldAlert className="h-3.5 w-3.5" /> : <ShieldCheck className="h-3.5 w-3.5" />}
              {meta.label}
            </span>
            {!unable &&
              (regulatory?.verified ? (
                <span className="chip bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200">
                  Verified official source
                </span>
              ) : (
                <span
                  className="chip bg-saffron-50 text-saffron-800 ring-1 ring-saffron-200"
                  title="This status belongs only to the synthetic demo corpus and is not an official regulatory claim."
                >
                  Demo regulatory status
                </span>
              ))}
          </div>

          {unable ? (
            <p
              className="mt-3 max-w-xl text-sm leading-relaxed text-ink-600"
              title="Regulatory status could not be confirmed from the currently loaded verified sources."
            >
              Regulatory status could not be confirmed from the currently loaded verified sources.
              This is not an error — the platform reports “unable to verify” rather than assuming a
              product is unregulated.
            </p>
          ) : (
            <div className="mt-3 space-y-0.5 text-sm text-ink-700">
              {regulatory?.qco_name && (
                <div className="font-semibold text-ink-900">{regulatory.qco_name}</div>
              )}
              {regulatory?.notification_number && (
                <div className="font-mono text-xs text-ink-500">{regulatory.notification_number}</div>
              )}
              <div className="flex flex-wrap gap-x-4 gap-y-0.5 text-xs text-ink-500">
                {regulatory?.notification_date && (
                  <span>Notified {formatDate(regulatory.notification_date)}</span>
                )}
                {regulatory?.effective_date && (
                  <span>Effective {formatDate(regulatory.effective_date)}</span>
                )}
                {regulatory?.ministry && <span>{regulatory.ministry}</span>}
              </div>
            </div>
          )}
        </div>

        {!unable && standardId && (
          <button className="btn-ghost btn-sm shrink-0" onClick={() => onView(standardId)}>
            <Gavel className="h-3.5 w-3.5" />
            View regulatory evidence
          </button>
        )}
      </div>
    </div>
  )
}
