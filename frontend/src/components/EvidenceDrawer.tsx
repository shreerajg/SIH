import { useEffect, useState } from 'react'
import { BookOpen, ExternalLink, FileText, X } from 'lucide-react'
import { api, apiError } from '@/lib/api'
import type { ClauseRef, SourceDetail } from '@/lib/types'
import { citationLabel, documentTypeMeta } from '@/lib/format'
import { DemoDataBadge, ErrorState } from './primitives'

/** Small inline citation button. Clicking it opens the full source.
 *
 *  A citation names the *kind* of document it came from whenever that is not a
 *  full Indian Standard, so BIS Product Manual or QCO text can never be read as
 *  Standard clause text.
 */
export function EvidenceCitation({
  citation,
  onOpen,
  className = '',
}: {
  citation: Pick<ClauseRef, 'chunk_id' | 'display_number' | 'clause_number' | 'page_number'> &
    Partial<Pick<ClauseRef, 'document_type' | 'document_title'>>
  onOpen: (chunkId: string) => void
  className?: string
}) {
  const kind = citation.document_type && citation.document_type !== 'standard'
    ? documentTypeMeta(citation.document_type)
    : null
  return (
    <button
      type="button"
      onClick={() => onOpen(citation.chunk_id)}
      className={`inline-flex items-center gap-1.5 rounded-lg border border-brand-200 bg-brand-50 px-2 py-1
                  text-[11px] font-semibold text-brand-800 transition-colors hover:bg-brand-100 ${className}`}
      title={
        kind
          ? `${kind.label}: ${kind.description}${citation.document_title ? ` (${citation.document_title})` : ''}`
          : 'Open the source clause'
      }
    >
      <BookOpen className="h-3 w-3" />
      {citationLabel(citation)}
      {kind && (
        <span className={`ml-0.5 rounded px-1 py-px text-[9px] font-bold uppercase tracking-wide ${kind.chip}`}>
          {kind.short}
        </span>
      )}
    </button>
  )
}

// Deterministic plain-language reading of one clause, used only when the clause
// literally contains the topic term — never invented. Kept in step with the
// backend findings vocabulary so the drawer and the summary agree.
const CLAUSE_MEANINGS: { keywords: string[]; meaning: string }[] = [
  { keywords: ['quality assurance plan', 'quality assurance', 'qap'], meaning: 'Describes the Quality Assurance Plan the manufacturer is expected to keep.' },
  { keywords: ['scheme of inspection and testing', 'inspection and testing'], meaning: 'Sets out the Scheme of Inspection and Testing for the product.' },
  { keywords: ['grouping', 'group of models'], meaning: 'Explains how products are grouped for certification.' },
  { keywords: ['sampling', 'sample size', 'sample quantity'], meaning: 'Defines how samples are drawn for testing.' },
  { keywords: ['standard mark', 'marking', 'labelling', 'labeling'], meaning: 'Covers marking and labelling, including the BIS Standard Mark.' },
  { keywords: ['levels of control', 'level of control', 'control unit'], meaning: 'Defines the recommended levels of control.' },
]

function plainMeaning(text: string): string | null {
  const t = (text || '').toLowerCase()
  for (const m of CLAUSE_MEANINGS) {
    if (m.keywords.some((k) => t.includes(k))) return m.meaning
  }
  return null
}

/** Slide-over panel showing the full text of a cited clause plus its siblings. */
export function EvidenceDrawer({
  chunkId,
  onClose,
  onNavigate,
}: {
  chunkId: string | null
  onClose: () => void
  onNavigate?: (chunkId: string) => void
}) {
  const [source, setSource] = useState<SourceDetail | null>(null)
  const [showRelated, setShowRelated] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!chunkId) return
    let cancelled = false
    setLoading(true)
    setError('')
    setSource(null)
    setShowRelated(false)
    api
      .getSource(chunkId)
      .then((data) => {
        if (!cancelled) setSource(data)
      })
      .catch((e) => {
        if (!cancelled) setError(apiError(e))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [chunkId])

  useEffect(() => {
    if (!chunkId) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [chunkId, onClose])

  if (!chunkId) return null

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div
        className="absolute inset-0 bg-ink-950/30 backdrop-blur-[2px]"
        onClick={onClose}
        aria-hidden
      />
      <aside className="relative flex h-full w-full max-w-xl flex-col bg-white shadow-panel animate-fade-up">
        <header className="flex items-start justify-between gap-4 border-b border-ink-200 px-6 py-4">
          <div className="min-w-0">
            <div className="section-title">Source evidence</div>
            <h2 className="mt-1 truncate text-base font-bold text-ink-900">
              {source ? citationLabel(source as never) : 'Loading source…'}
            </h2>
          </div>
          <button className="btn-ghost btn-sm shrink-0" onClick={onClose} aria-label="Close">
            <X className="h-4 w-4" />
          </button>
        </header>

        <div className="scroll-thin flex-1 overflow-y-auto px-6 py-5">
          {loading && (
            <div className="space-y-3">
              <div className="skeleton h-4 w-2/3" />
              <div className="skeleton h-3 w-full" />
              <div className="skeleton h-3 w-full" />
              <div className="skeleton h-3 w-3/4" />
            </div>
          )}

          {error && <ErrorState message={error} />}

          {source && (
            <div className="space-y-5">
              <section className="card p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="chip bg-ink-100 text-ink-700">{source.standard.display_number}</span>
                  <span
                    className={`chip ${documentTypeMeta(source.standard.document_type).chip}`}
                    title={documentTypeMeta(source.standard.document_type).description}
                  >
                    {documentTypeMeta(source.standard.document_type).label}
                  </span>
                  {source.standard.is_mock && <DemoDataBadge compact />}
                  {source.standard.version && (
                    <span className="text-xs text-ink-500">Version {source.standard.version}</span>
                  )}
                </div>
                <h3 className="mt-2 text-sm font-semibold text-ink-900">{source.standard.title}</h3>
                {source.standard.source_url ? (
                  <a
                    className="link mt-2 inline-flex items-center gap-1 text-xs"
                    href={source.standard.source_url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    <ExternalLink className="h-3 w-3" />
                    Official source
                  </a>
                ) : (
                  <p className="mt-2 text-xs text-ink-400">
                    No official source URL — this document is part of the demonstration corpus.
                  </p>
                )}
              </section>

              <section>
                <div className="section-title mb-2">
                  Clause {source.clause_number}
                  {source.page_number && source.page_number > 0 ? ` · Page ${source.page_number}` : ''}
                </div>
                {source.heading && (
                  <p className="mb-2 text-sm font-semibold text-ink-800">{source.heading}</p>
                )}
                {plainMeaning(source.text) && (
                  <p className="mb-2 rounded-lg bg-emerald-50 px-3 py-2 text-sm leading-relaxed text-emerald-900 ring-1 ring-emerald-100">
                    <span className="font-semibold">In plain terms: </span>
                    {plainMeaning(source.text)}
                  </p>
                )}
                <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-ink-400">
                  Exact source text
                </div>
                <blockquote className="rounded-xl border-l-4 border-brand-400 bg-brand-50/40 px-4 py-3 text-sm leading-relaxed text-ink-800">
                  {source.text}
                </blockquote>
              </section>

              {source.neighbours.length > 0 && (
                <section>
                  <button
                    className="btn-secondary btn-sm"
                    onClick={() => setShowRelated((v) => !v)}
                    aria-expanded={showRelated}
                  >
                    {showRelated ? 'Hide' : 'View'} {source.neighbours.length} related clause
                    {source.neighbours.length === 1 ? '' : 's'}
                  </button>
                  {showRelated && (
                    <ul className="mt-3 space-y-2">
                      {source.neighbours.map((n) => (
                        <li key={n.chunk_id}>
                          <button
                            type="button"
                            onClick={() => onNavigate?.(n.chunk_id)}
                            className="w-full rounded-xl border border-ink-200 px-3.5 py-2.5 text-left transition-colors hover:border-brand-300 hover:bg-brand-50/40"
                          >
                            <div className="flex items-center gap-2 text-xs font-semibold text-ink-700">
                              <FileText className="h-3.5 w-3.5 text-ink-400" />
                              Clause {n.clause_number}
                            </div>
                            <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-ink-500">
                              {n.excerpt}
                            </p>
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </section>
              )}
            </div>
          )}
        </div>
      </aside>
    </div>
  )
}

/** Hook that wires the drawer into any page with two lines. */
export function useEvidenceDrawer() {
  const [chunkId, setChunkId] = useState<string | null>(null)
  return {
    chunkId,
    open: setChunkId,
    close: () => setChunkId(null),
  }
}
