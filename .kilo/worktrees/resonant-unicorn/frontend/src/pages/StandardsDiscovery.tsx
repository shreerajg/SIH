import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  ArrowRight,
  CheckCircle2,
  FileSearch,
  Layers,
  Link2,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
} from 'lucide-react'
import { api, apiError } from '@/lib/api'
import type { PlainFinding, StandardMatch } from '@/lib/types'
import { REGULATORY_META, titleCase } from '@/lib/format'
import { StandardCard } from '@/components/StandardCard'
import { EvidenceDrawer, useEvidenceDrawer } from '@/components/EvidenceDrawer'
import { RegulatoryDrawer } from '@/components/RegulatoryDrawer'
import { RegulatoryCard } from '@/components/RegulatoryCard'
import { EmptyState, ErrorState, LoadingSkeleton, SectionHeading } from '@/components/primitives'

// Human wording for a stored standard-to-standard relationship. Only these
// come from the corpus's StandardRelationship records — never invented.
const RELATIONSHIP_LABELS: Record<string, string> = {
  references_test_method: 'Referenced test method',
  references_safety_standard: 'Referenced safety standard',
  references_marking_standard: 'Referenced marking standard',
  companion_part: 'Companion part',
  amended_by: 'Amended by',
  superseded_by: 'Superseded by',
}

// The rule engine's own ordering; used only to pick the strongest match.
const RELEVANCE_RANK: Record<string, number> = {
  HIGH: 0,
  NEEDS_VERIFICATION: 1,
  MEDIUM: 2,
  LOW: 3,
}

function isRegulatoryDoc(m: StandardMatch): boolean {
  return m.standard.document_type === 'qco' || m.standard.document_type === 'regulatory'
}

function isCrossFamily(m: StandardMatch): boolean {
  return m.signals?.cross_family_penalised === true
}

/** The explicit, stored reason a document is related — or null if there is none. */
function relationshipOf(m: StandardMatch): { label: string; evidence: string } | null {
  const via = typeof m.signals?.via_relationship === 'string' ? (m.signals.via_relationship as string) : ''
  const note = m.matched_attributes.find((a) => a.attribute === 'normative reference')?.note
  if (via) {
    return { label: RELATIONSHIP_LABELS[via] ?? titleCase(via.replace(/_/g, ' ')), evidence: note ?? m.reason }
  }
  if (m.explanation_source === 'relationship_graph') {
    return { label: 'Normative reference', evidence: note ?? m.reason }
  }
  return null
}

export function StandardsDiscovery() {
  const { productId = '' } = useParams()
  const navigate = useNavigate()
  const drawer = useEvidenceDrawer()
  const [regulatoryFor, setRegulatoryFor] = useState<string | null>(null)
  const [matches, setMatches] = useState<StandardMatch[]>([])
  const [notes, setNotes] = useState<string[]>([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [findings, setFindings] = useState<PlainFinding[]>([])
  const [findingsNote, setFindingsNote] = useState('')

  const load = useCallback(() => {
    setLoading(true)
    setError('')
    api
      .getProductStandards(productId)
      .then((d) => {
        setMatches(d.matches)
        setNotes(d.notes)
      })
      .catch((e) => setError(apiError(e)))
      .finally(() => setLoading(false))
  }, [productId])

  useEffect(load, [load])

  const rerun = async () => {
    setLoading(true)
    setError('')
    try {
      const d = await api.discoverStandards(productId)
      setMatches(d.matches)
      setNotes(d.notes)
    } catch (e) {
      setError(apiError(e))
    } finally {
      setLoading(false)
    }
  }

  const groups = useMemo(() => {
    // Judge-facing flow shows verified official sources only. The demo corpus
    // still exists for development, testing, evaluation and fallback — it is
    // simply not surfaced here. Verified-source prioritisation is unchanged.
    const standardLike = matches.filter((m) => m.standard.is_verified && !isRegulatoryDoc(m))

    const rank = (m: StandardMatch) => RELEVANCE_RANK[m.relevance] ?? 4
    const better = (a: StandardMatch, b: StandardMatch) => {
      if (rank(a) !== rank(b)) return rank(a) - rank(b)
      return b.score - a.score
    }

    const primaryPool = standardLike.filter((m) => !isCrossFamily(m))
    const primary = [...(primaryPool.length ? primaryPool : standardLike)].sort(better)[0] ?? null

    // Related = an explicit stored relationship, or a strong same-family
    // verified source. Cross-family and weak candidates are not surfaced.
    const related = standardLike.filter(
      (m) =>
        m !== primary &&
        (relationshipOf(m) !== null || (!isCrossFamily(m) && m.relevance !== 'LOW')),
    )

    const verifiedCount = (primary ? 1 : 0) + related.length
    return { primary, related, verifiedCount, regulatory: primary?.regulatory ?? null }
  }, [matches])

  const { primary, related, verifiedCount, regulatory } = groups
  const primaryId = primary?.standard.id ?? ''

  // Plain-language findings for the primary source, fetched from the backend's
  // deterministic, clause-cited extractor — never generated in the browser.
  useEffect(() => {
    if (!primaryId) {
      setFindings([])
      setFindingsNote('')
      return
    }
    let cancelled = false
    api
      .standardFindings(primaryId)
      .then((d) => {
        if (!cancelled) {
          setFindings(d.findings)
          setFindingsNote(d.note)
        }
      })
      .catch(() => {
        if (!cancelled) {
          setFindings([])
          setFindingsNote('')
        }
      })
    return () => {
      cancelled = true
    }
  }, [primaryId])

  // Recommended next actions, derived only from current state + findings.
  const nextActions: string[] = []
  if (findings.some((f) => f.key === 'quality_assurance_plan'))
    nextActions.push('Review your Quality Assurance Plan against this source.')
  if (findings.some((f) => f.key === 'tests' || f.key === 'inspection_and_testing'))
    nextActions.push('Gather and upload existing test reports as product evidence.')
  if (regulatory && regulatory.status !== 'UNABLE_TO_VERIFY')
    nextActions.push(`Review the regulatory evidence behind the ${REGULATORY_META[regulatory.status].label} status.`)
  nextActions.push('Open the Pre-Compliance Gap Analyzer to check each requirement against what you can evidence.')

  return (
    <div className="mx-auto max-w-5xl px-4 py-12 sm:px-6">
      <div className="flex items-center gap-2.5">
        <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand-50 text-brand-600">
          <Layers className="h-4.5 w-4.5" />
        </span>
        <span className="section-title">Step 2 of 4 · Applicable standards</span>
      </div>

      <h1 className="mt-4 text-3xl font-extrabold tracking-tight text-ink-900">Standards landscape</h1>
      <p className="mt-2 max-w-2xl text-sm leading-relaxed text-ink-500">
        Retrieved using hybrid keyword and semantic search, then organised into applicable,
        regulatory and supporting sources.
      </p>

      {loading && <div className="mt-8"><LoadingSkeleton rows={3} /></div>}
      {error && !loading && <div className="mt-8"><ErrorState message={error} onRetry={load} /></div>}

      {!loading && !error && matches.length === 0 && (
        <div className="mt-8">
          <EmptyState
            title="No applicable standard identified yet"
            description="We couldn't confidently match this product to a document in the current corpus. Add more product detail, or ingest the relevant standards documents."
            action={
              <Link to={`/product-analysis/${productId}`} className="btn-secondary btn-sm">
                Add more product detail
              </Link>
            }
          />
        </div>
      )}

      {!loading && !error && matches.length > 0 && (
        <>
          {/* Simple verified-source status + re-run on one row */}
          <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
            <span className="chip bg-white text-ink-700 ring-1 ring-ink-200">
              <ShieldCheck className="h-3.5 w-3.5 text-emerald-500" />
              {verifiedCount > 0
                ? `${verifiedCount} verified source${verifiedCount === 1 ? '' : 's'} identified for this product`
                : 'No verified official source identified for this product yet'}
            </span>
            <button className="btn-secondary btn-sm" onClick={rerun} disabled={loading}>
              <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
              Re-run discovery
            </button>
          </div>

          {notes.map((note) => (
            <div
              key={note}
              className="mt-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900"
            >
              {note}
            </div>
          ))}

          {/* PRIMARY */}
          <section className="mt-8">
            <SectionHeading
              title="Primary applicable source"
              description="The strongest verified source for this product."
            />
            {primary ? (
              <StandardCard
                match={primary}
                onOpenSource={drawer.open}
                onViewRequirements={(id) => navigate(`/standards/${id}`)}
                onAsk={(id) => navigate(`/assistant?standard=${id}&product=${productId}`)}
                hideRegulatoryBadge
              />
            ) : (
              <div className="card p-5">
                <p className="text-sm leading-relaxed text-ink-600">
                  No verified official source is loaded for this product yet.
                </p>
              </div>
            )}
          </section>

          {/* WHAT THIS MEANS — plain-language, source-grounded findings */}
          {primary && (
            <section className="mt-8">
              <SectionHeading
                title="What this means for your product"
                description="Read from the source document itself — each point links to the exact clause it came from."
              />
              <div className="card p-5">
                {findings.length > 0 ? (
                  <ul className="space-y-2.5">
                    {findings.map((f) => (
                      <li key={f.key} className="flex items-start gap-2.5">
                        <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-500" />
                        <div className="min-w-0">
                          <p className="text-sm leading-relaxed text-ink-700">{f.text}</p>
                          <button
                            className="mt-0.5 inline-flex items-center gap-1 text-xs font-semibold text-brand-700 hover:underline"
                            onClick={() => drawer.open(f.chunk_id)}
                          >
                            <FileSearch className="h-3 w-3" />
                            Clause {f.clause_number}
                            {f.page_number ? ` · Page ${f.page_number}` : ''}
                          </button>
                        </div>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm leading-relaxed text-ink-600">
                    {findingsNote ||
                      'Unable to verify additional product-specific requirements from the currently loaded verified source.'}
                  </p>
                )}

                {/* Trust row — only badges that are true */}
                <div className="mt-4 flex flex-wrap gap-2 border-t border-ink-100 pt-3.5">
                  {primary.standard.is_verified && (
                    <span className="chip bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200">
                      <ShieldCheck className="h-3.5 w-3.5" />
                      Verified official source
                    </span>
                  )}
                  {regulatory && regulatory.status !== 'UNABLE_TO_VERIFY' ? (
                    <span className="chip bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200">
                      <ShieldCheck className="h-3.5 w-3.5" />
                      Regulatory evidence available
                    </span>
                  ) : (
                    <span className="chip bg-ink-100 text-ink-500 ring-1 ring-ink-200">
                      <ShieldAlert className="h-3.5 w-3.5" />
                      Regulatory status unable to verify
                    </span>
                  )}
                  {findings.length > 0 && (
                    <span className="chip bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200">
                      <ShieldCheck className="h-3.5 w-3.5" />
                      Clause-level evidence available
                    </span>
                  )}
                </div>
              </div>
            </section>
          )}

          {/* REGULATORY */}
          <section className="mt-8">
            <SectionHeading
              title="Regulatory status"
              description="Read from structured Quality Control Order records only — never inferred from a standard's text."
            />
            <RegulatoryCard
              regulatory={regulatory}
              standardId={primary?.standard.id ?? null}
              onView={setRegulatoryFor}
            />
          </section>

          {/* RELATED — only when genuinely present */}
          {related.length > 0 && (
            <section className="mt-8">
              <SectionHeading
                title="Related & supporting standards"
                description="Included only where the corpus records an explicit relationship or a verified source in the same product family."
              />
              <div className="space-y-4">
                {related.map((m) => {
                  const rel = relationshipOf(m)
                  return (
                    <div key={m.standard.id}>
                      <div className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold text-ink-500">
                        <Link2 className="h-3.5 w-3.5 text-brand-500" />
                        {rel ? rel.label : 'Same product family · verified official source'}
                      </div>
                      <StandardCard
                        match={m}
                        onOpenSource={drawer.open}
                        onViewRequirements={(id) => navigate(`/standards/${id}`)}
                        onAsk={(id) => navigate(`/assistant?standard=${id}&product=${productId}`)}
                        hideRegulatoryBadge
                      />
                    </div>
                  )
                })}
              </div>
            </section>
          )}

          {/* NEXT STEP + recommended actions */}
          <section className="mt-8">
            <SectionHeading
              title="Recommended next actions"
              description="Based on the current evidence and system state — pre-compliance preparation, not a certification result."
            />
            {primary && nextActions.length > 0 && (
              <ol className="mb-4 space-y-1.5">
                {nextActions.map((action, i) => (
                  <li key={action} className="flex items-start gap-2.5 text-sm text-ink-700">
                    <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-brand-50 text-[11px] font-bold text-brand-700 tabular-nums">
                      {i + 1}
                    </span>
                    {action}
                  </li>
                ))}
              </ol>
            )}
            <div className="card flex flex-wrap items-center justify-between gap-4 p-5">
              <div>
                <h3 className="text-base font-bold text-ink-900">Run pre-compliance analysis</h3>
                <p className="mt-1 max-w-xl text-sm leading-relaxed text-ink-600">
                  Declare your design values and list the evidence you hold. The analyzer walks every
                  requirement and tells you which are supported and which need work.
                </p>
              </div>
              <Link to={`/product/${productId}/gap-analysis`} className="btn-primary">
                Open gap analyzer
                <ArrowRight className="h-4 w-4" />
              </Link>
            </div>
          </section>
        </>
      )}

      <EvidenceDrawer chunkId={drawer.chunkId} onClose={drawer.close} onNavigate={drawer.open} />
      <RegulatoryDrawer standardId={regulatoryFor} onClose={() => setRegulatoryFor(null)} />
    </div>
  )
}

