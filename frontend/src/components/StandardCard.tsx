import { useState } from 'react'
import { ChevronDown, FileSearch, Gavel, MessageSquare, ScrollText, Sparkles, Target } from 'lucide-react'
import type { StandardMatch } from '@/lib/types'
import { documentTypeMeta } from '@/lib/format'
import { DemoDataBadge, RegulatoryBadge, RelevanceBadge } from './primitives'
import { MatchScoreBreakdown } from './MatchScoreBreakdown'

/** A plain-English reason, built only from the real matched attributes — never
 *  the raw retrieval wording. Falls back to the deterministic reason. */
function plainWhy(match: StandardMatch): string {
  const kind = documentTypeMeta(match.standard.document_type).label
  const attrs = [
    ...new Set(
      match.matched_attributes
        .map((a) => a.attribute)
        .filter((a) => a && a !== 'normative reference'),
    ),
  ].slice(0, 4)
  if (attrs.length === 0) return match.reason
  const list =
    attrs.length === 1
      ? attrs[0]
      : `${attrs.slice(0, -1).join(', ')} and ${attrs[attrs.length - 1]}`
  return `This ${kind} applies to your product because it matches on ${list}.`
}

export function StandardCard({
  match,
  onOpenSource,
  onAsk,
  onViewRequirements,
  onViewRegulatory,
  hideRegulatoryBadge = false,
}: {
  match: StandardMatch
  onOpenSource: (chunkId: string) => void
  onAsk?: (standardId: string) => void
  onViewRequirements?: (standardId: string) => void
  onViewRegulatory?: (standardId: string) => void
  /** Discovery groups regulatory status into its own section, so the inline
   *  header badge is suppressed there to avoid saying it twice. */
  hideRegulatoryBadge?: boolean
}) {
  const [showTech, setShowTech] = useState(false)
  const { standard, regulatory } = match
  const passages = match.evidence_clauses.length

  return (
    <article className="card card-hover overflow-hidden">
      <div className="p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-lg bg-ink-900 px-2 py-1 font-mono text-xs font-bold text-white">
                {standard.display_number}
              </span>
              <RelevanceBadge relevance={match.relevance} />
              <span
                className={`chip ${documentTypeMeta(standard.document_type).chip}`}
                title={documentTypeMeta(standard.document_type).description}
              >
                {documentTypeMeta(standard.document_type).label}
              </span>
              {standard.is_verified && (
                <span
                  className="chip bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200"
                  title={
                    standard.source_url
                      ? `Official source: ${standard.source_url}`
                      : 'Official source document'
                  }
                >
                  Verified official source
                </span>
              )}
              {standard.is_mock && <DemoDataBadge compact />}
            </div>
            <h3 className="mt-2.5 text-base font-bold leading-snug text-ink-900">{standard.title}</h3>
          </div>
          {!hideRegulatoryBadge && (
            <RegulatoryBadge status={regulatory.status} verified={regulatory.verified} />
          )}
        </div>

        {/* WHY THIS APPLIES — plain English, always visible */}
        <div className="mt-3">
          <div className="section-title mb-1">Why this applies</div>
          <p className="text-sm leading-relaxed text-ink-600">{plainWhy(match)}</p>
        </div>

        {match.matched_attributes.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {match.matched_attributes.slice(0, 6).map((attr, i) => (
              <span
                key={`${attr.attribute}-${i}`}
                className="chip bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200"
                title={attr.note}
              >
                <Target className="h-3 w-3" />
                {attr.attribute}
              </span>
            ))}
            {match.matched_attributes.length > 6 && (
              <span className="chip bg-ink-100 text-ink-500">
                +{match.matched_attributes.length - 6} more
              </span>
            )}
          </div>
        )}

        <div className="mt-4 flex flex-wrap items-center gap-2">
          {passages > 0 && (
            <button
              className="btn-secondary btn-sm"
              onClick={() => onOpenSource(match.evidence_clauses[0].chunk_id)}
              title="Open the exact clauses this match is based on"
            >
              <FileSearch className="h-3.5 w-3.5" />
              {passages} supporting source passage{passages === 1 ? '' : 's'}
            </button>
          )}
          <button className="btn-ghost btn-sm" onClick={() => setShowTech((v) => !v)}>
            <Sparkles className="h-3.5 w-3.5" />
            View technical match details
            <ChevronDown className={`h-3.5 w-3.5 transition-transform ${showTech ? 'rotate-180' : ''}`} />
          </button>
          {onViewRequirements && (
            <button
              className="btn-ghost btn-sm"
              onClick={() => onViewRequirements(standard.id)}
              title={
                standard.requirement_count === 0
                  ? 'No structured requirements were extracted from this source; opens the document and its clauses.'
                  : undefined
              }
            >
              <ScrollText className="h-3.5 w-3.5" />
              {standard.requirement_count === 0 ? 'View document' : 'View requirements'}
              {standard.requirement_count > 0 && (
                <span className="ml-0.5 rounded bg-ink-100 px-1.5 text-[10px] font-bold text-ink-500">
                  {standard.requirement_count}
                </span>
              )}
            </button>
          )}
          {onAsk && (
            <button className="btn-ghost btn-sm" onClick={() => onAsk(standard.id)}>
              <MessageSquare className="h-3.5 w-3.5" />
              Ask about this standard
            </button>
          )}
          {onViewRegulatory && (
            <button className="btn-ghost btn-sm" onClick={() => onViewRegulatory(standard.id)}>
              <Gavel className="h-3.5 w-3.5" />
              View regulatory evidence
            </button>
          )}
        </div>
      </div>

      {/* TECHNICAL DETAIL — collapsed by default */}
      {showTech && (
        <div className="animate-fade-up border-t border-ink-200 bg-ink-50/60 px-5 py-5">
          <div className="mb-5">
            <div className="section-title mb-2">How this was ranked</div>
            <MatchScoreBreakdown
              signals={match.signals}
              score={match.score}
              explanationSource={match.explanation_source}
            />
          </div>

          <div>
            <div className="section-title mb-2">
              Source text ({documentTypeMeta(standard.document_type).label})
            </div>
            <blockquote className="rounded-xl border-l-4 border-brand-400 bg-white px-3.5 py-3 text-sm leading-relaxed text-ink-700">
              {match.scope_evidence || 'No supporting text was recorded for this source.'}
            </blockquote>
          </div>

          <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-1.5 border-t border-ink-200 pt-3 text-xs text-ink-500">
            <span>
              Explanation from:{' '}
              <span className="font-semibold text-ink-700">
                {match.explanation_source === 'llm'
                  ? 'language model, constrained to retrieved candidates'
                  : match.explanation_source === 'relationship_graph'
                    ? 'normative reference in a matched standard'
                    : 'deterministic keyword and text matching'}
              </span>
            </span>
            <span>
              Regulatory status source:{' '}
              <span className="font-semibold text-ink-700">
                {regulatory.source ?? 'no record found'}
              </span>
            </span>
          </div>
        </div>
      )}
    </article>
  )
}
