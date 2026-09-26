/**
 * Visualises the retrieval signals behind a standard match.
 *
 * The three scores are computed by the same hybrid retriever for every
 * standard in the corpus (app/search/hybrid.py) — nothing here is invented
 * for display. A relationship-graph match (pulled in because a matched
 * standard names it as a normative reference) was never scored by retrieval
 * at all, so it gets an explanatory note instead of fabricated bars.
 */
const SIGNAL_META: {
  key: 'semantic' | 'bm25' | 'metadata'
  label: string
  color: string
  description: string
}[] = [
  {
    key: 'semantic',
    label: 'Semantic similarity',
    color: 'bg-brand-500',
    description:
      "How close the product description is to this standard's text by meaning, using sentence embeddings — not just shared words.",
  },
  {
    key: 'bm25',
    label: 'Keyword match',
    color: 'bg-emerald-500',
    description:
      'Exact and near-exact term overlap between the product description and this standard, ranked by BM25.',
  },
  {
    key: 'metadata',
    label: 'Category & keyword fit',
    color: 'bg-amber-500',
    description:
      "Overlap with this standard's declared keyword list, and whether the product's category matches the standard's product family.",
  },
]

export function MatchScoreBreakdown({
  signals,
  score,
  explanationSource,
}: {
  signals: Record<string, unknown>
  score: number
  explanationSource: string
}) {
  const hasSignals = typeof signals.semantic === 'number'

  if (!hasSignals) {
    return (
      <div className="rounded-lg bg-white px-3 py-2.5 text-xs leading-relaxed text-ink-500 ring-1 ring-ink-200">
        {explanationSource === 'relationship_graph'
          ? 'This standard was not scored by retrieval — it was pulled in because a matched standard names it as a normative reference (see the reason above).'
          : 'No retrieval signal was recorded for this match.'}
      </div>
    )
  }

  return (
    <div>
      <div className="space-y-2.5">
        {SIGNAL_META.map(({ key, label, color, description }) => {
          const value = Number(signals[key] ?? 0)
          const pct = Math.round(Math.max(0, Math.min(1, value)) * 100)
          return (
            <div key={key} title={description}>
              <div className="flex items-center justify-between text-[11px] font-semibold text-ink-600">
                <span>{label}</span>
                <span className="tabular-nums text-ink-400">{pct}%</span>
              </div>
              <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-ink-100">
                <div
                  className={`h-full rounded-full ${color} transition-all`}
                  style={{ width: `${pct}%` }}
                />
              </div>
            </div>
          )
        })}
      </div>
      <p className="mt-2.5 text-[11px] leading-relaxed text-ink-400">
        Combined match score:{' '}
        <span className="font-semibold text-ink-600">{Math.round(score * 100)}%</span> — a weighted
        blend of the three signals above, scored the same way for every standard in the corpus.
        {Boolean(signals.cross_family_penalised) && (
          <> This standard is outside the product's category, so its score was penalised.</>
        )}
      </p>
    </div>
  )
}
