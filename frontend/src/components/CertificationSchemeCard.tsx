import { useState } from 'react'
import {
  Award,
  BadgeCheck,
  ChevronDown,
  ExternalLink,
  FileText,
  ShieldAlert,
} from 'lucide-react'
import type { SchemeGuidance } from '@/lib/types'

/**
 * "Applicable Certification Scheme" — the manufacturer-facing summary of which
 * BIS scheme applies to a product and why.
 *
 * Every statement here comes from a stored record the backend resolved; this
 * component only renders what it was given. In particular it never infers a
 * scheme, and an `UNABLE_TO_VERIFY` determination is shown as exactly that
 * rather than being hidden or softened into a suggestion — the same contract
 * RegulatoryCard follows for mandatory/voluntary status.
 */

const APPLICABILITY_META: Record<
  SchemeGuidance['applicability'],
  { label: string; chip: string; verified: boolean }
> = {
  APPLICABLE: {
    label: 'Applicable scheme identified',
    chip: 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200',
    verified: true,
  },
  LIKELY: {
    label: 'Indicated by demo records',
    chip: 'bg-saffron-50 text-saffron-800 ring-1 ring-saffron-200',
    verified: false,
  },
  UNABLE_TO_VERIFY: {
    label: 'Unable to verify',
    chip: 'bg-ink-100 text-ink-700 ring-1 ring-ink-200',
    verified: false,
  },
}

function Detail({ label, value }: { label: string; value: string | null }) {
  if (!value) return null
  return (
    <div>
      <dt className="text-xs font-medium uppercase tracking-wide text-ink-500">{label}</dt>
      <dd className="mt-0.5 text-sm leading-relaxed text-ink-700">{value}</dd>
    </div>
  )
}

export function CertificationSchemeCard({
  guidance,
  note,
  onContinue,
}: {
  guidance: SchemeGuidance | null
  note?: string
  onContinue?: () => void
}) {
  const [expanded, setExpanded] = useState(false)

  const applicability = guidance?.applicability ?? 'UNABLE_TO_VERIFY'
  const meta = APPLICABILITY_META[applicability]
  const scheme = guidance?.scheme ?? null
  const unable = applicability === 'UNABLE_TO_VERIFY' || scheme === null

  return (
    <div className="card p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className={`chip ${meta.chip}`}>
              {unable ? (
                <ShieldAlert className="h-3.5 w-3.5" />
              ) : (
                <Award className="h-3.5 w-3.5" />
              )}
              {meta.label}
            </span>
            {scheme?.is_verified && (
              <span className="chip bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200">
                <BadgeCheck className="h-3.5 w-3.5" />
                Verified official source
              </span>
            )}
          </div>

          <h3 className="mt-3 text-lg font-semibold text-ink-900">
            {scheme ? scheme.name : 'Applicable Certification Scheme'}
          </h3>

          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-ink-600">
            {guidance?.message || note || 'No certification scheme has been resolved yet.'}
          </p>

          {scheme?.mark && (
            <p className="mt-2 text-sm text-ink-700">
              <span className="font-medium">Mark:</span> {scheme.mark}
            </p>
          )}
        </div>

        {scheme && onContinue && (
          <button type="button" className="btn-primary shrink-0" onClick={onContinue}>
            Certification process guidance
          </button>
        )}
      </div>

      {/* --- why it applies --------------------------------------------- */}
      {guidance && guidance.reasons.length > 0 && (
        <div className="mt-4 rounded-lg bg-ink-50/70 p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-ink-500">
            Why this scheme applies
          </p>
          <ul className="mt-2 space-y-2">
            {guidance.reasons.map((reason, i) => (
              <li key={i} className="text-sm leading-relaxed text-ink-700">
                <span className="font-medium text-ink-900">{reason.factor}:</span>{' '}
                {reason.detail}
                {!reason.is_verified && (
                  <span className="ml-1 text-xs text-saffron-700">(demo record)</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* --- source citations -------------------------------------------- */}
      {guidance && guidance.evidence.length > 0 && (
        <div className="mt-4">
          <p className="text-xs font-medium uppercase tracking-wide text-ink-500">Sources</p>
          <ul className="mt-2 space-y-1.5">
            {guidance.evidence.map((item, i) => (
              <li key={i} className="flex flex-wrap items-center gap-2 text-sm text-ink-700">
                <FileText className="h-3.5 w-3.5 shrink-0 text-ink-400" />
                <span>{item.label}</span>
                {item.retrieved_at && (
                  <span className="text-xs text-ink-500">retrieved {item.retrieved_at}</span>
                )}
                {item.source_url && (
                  <a
                    href={item.source_url}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 text-xs font-medium text-saffron-700 hover:underline"
                  >
                    View source <ExternalLink className="h-3 w-3" />
                  </a>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* --- scheme detail ------------------------------------------------ */}
      {scheme && (
        <div className="mt-4 border-t border-ink-100 pt-3">
          <button
            type="button"
            className="inline-flex items-center gap-1.5 text-sm font-medium text-ink-700 hover:text-ink-900"
            onClick={() => setExpanded((v) => !v)}
            aria-expanded={expanded}
          >
            <ChevronDown
              className={`h-4 w-4 transition-transform ${expanded ? 'rotate-180' : ''}`}
            />
            {expanded ? 'Hide scheme details' : 'Scheme details'}
          </button>

          {expanded && (
            <div className="mt-3 space-y-3">
              <dl className="grid gap-3 sm:grid-cols-2">
                <Detail label="Purpose" value={scheme.purpose} />
                <Detail label="Who it applies to" value={scheme.applies_to} />
                <Detail label="Product applicability" value={scheme.product_applicability} />
                <Detail label="Legal basis" value={scheme.legal_basis} />
                <Detail label="Testing requirement" value={scheme.testing_requirement} />
              </dl>

              {scheme.key_documents.length > 0 && (
                <div>
                  <p className="text-xs font-medium uppercase tracking-wide text-ink-500">
                    Important documents
                  </p>
                  <ul className="mt-1 list-inside list-disc space-y-0.5 text-sm text-ink-700">
                    {scheme.key_documents.map((doc) => (
                      <li key={doc}>{doc}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Unsourced fields are named, never quietly omitted. */}
              {scheme.unavailable_fields.length > 0 && (
                <p className="rounded-lg bg-ink-50 p-3 text-xs leading-relaxed text-ink-600">
                  <span className="font-medium">{scheme.unavailable_note}</span> for:{' '}
                  {scheme.unavailable_fields.map((f) => f.replace(/_/g, ' ')).join(', ')}. These
                  are shown only when they have been transcribed from an official BIS document.
                </p>
              )}

              {scheme.source_url && (
                <a
                  href={scheme.source_url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 text-sm font-medium text-saffron-700 hover:underline"
                >
                  Official BIS page <ExternalLink className="h-3.5 w-3.5" />
                </a>
              )}
            </div>
          )}
        </div>
      )}

      <p className="mt-4 text-xs leading-relaxed text-ink-500">
        Scheme applicability is resolved from stored Quality Control Order records and the
        official BIS list of products under compulsory certification. It is never inferred from
        the product description, and where no record names a scheme the platform reports
        “unable to verify” rather than guessing.
      </p>
    </div>
  )
}
