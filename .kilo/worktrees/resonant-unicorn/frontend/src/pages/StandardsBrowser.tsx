import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  ArrowLeft,
  BookMarked,
  CheckCircle2,
  ChevronDown,
  ExternalLink,
  FileSearch,
  Layers,
  Library,
  Search,
  ShieldCheck,
} from 'lucide-react'
import { api, apiError } from '@/lib/api'
import type {
  PlainFinding,
  StandardDetail,
  StandardRequirement,
  StandardSummary,
} from '@/lib/types'
import { CATEGORY_LABELS, documentTypeMeta, titleCase } from '@/lib/format'
import { EvidenceDrawer, useEvidenceDrawer } from '@/components/EvidenceDrawer'
import { RegulatoryCard } from '@/components/RegulatoryCard'
import { RegulatoryDrawer } from '@/components/RegulatoryDrawer'
import {
  DemoDataBadge,
  ErrorState,
  LoadingSkeleton,
  RegulatoryBadge,
  SectionHeading,
} from '@/components/primitives'

// ---------------------------------------------------------------------------
// Standards & Regulatory Library (list)
// ---------------------------------------------------------------------------

/**
 * The corpus holds several different kinds of record and they are not
 * interchangeable: a Quality Control Order is not an Indian Standard, and a BIS
 * Product Manual is not the standard text it describes. The library groups by
 * document type, and — unlike a raw corpus browser — verified official sources
 * lead by default, with the synthetic demo dataset kept out of the way behind
 * an explicit advanced control.
 */
type GroupKey = 'product_manual' | 'regulatory' | 'standard' | 'supporting' | 'amendment'

interface GroupSpec {
  key: GroupKey
  label: string
  blurb: string
  matches: (s: StandardSummary) => boolean
}

const GROUPS: GroupSpec[] = [
  {
    key: 'product_manual',
    label: 'Verified Product Manuals',
    blurb: 'Official certification guidance — sampling, testing, marking. Not the full text of the standard it covers.',
    matches: (s) => s.document_type === 'product_manual',
  },
  {
    key: 'regulatory',
    label: 'Regulatory / Quality Control Orders',
    blurb: 'Gazette orders that make a standard mandatory. These are law, not standards.',
    matches: (s) => s.document_type === 'qco' || s.document_type === 'regulatory',
  },
  {
    key: 'standard',
    label: 'Indian Standards',
    blurb: 'Specification documents — structured requirements are extracted from these.',
    matches: (s) => s.document_type === 'standard' && s.product_category !== 'test-method',
  },
  {
    key: 'supporting',
    label: 'Test Methods',
    blurb: 'Horizontal standards and supporting documents that other records defer to.',
    matches: (s) =>
      (s.document_type === 'standard' && s.product_category === 'test-method') ||
      ['other', 'gazette', 'scheme_of_inspection_and_testing'].includes(s.document_type),
  },
  {
    key: 'amendment',
    label: 'Amendments',
    blurb: 'Changes to part of a standard, not the whole of one.',
    matches: (s) => s.document_type === 'amendment',
  },
]

type FilterKey = 'verified' | 'product_manual' | 'regulatory' | 'supporting' | 'all'

const FILTER_CHIPS: { key: FilterKey; label: string }[] = [
  { key: 'verified', label: 'Verified Sources' },
  { key: 'product_manual', label: 'Product Manuals' },
  { key: 'regulatory', label: 'Regulatory / QCO' },
  { key: 'supporting', label: 'Test Methods' },
  { key: 'all', label: 'All' },
]

export function StandardsBrowser() {
  const [documents, setDocuments] = useState<StandardSummary[]>([])
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<FilterKey>('verified')
  const [showDemo, setShowDemo] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api
      .listStandards()
      .then(setDocuments)
      .catch((e) => setError(apiError(e)))
      .finally(() => setLoading(false))
  }, [])

  const searched = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return documents
    return documents.filter(
      (s) =>
        s.title.toLowerCase().includes(q) ||
        s.is_number.toLowerCase().includes(q) ||
        s.display_number.toLowerCase().includes(q) ||
        s.keywords.some((k) => k.includes(q)),
    )
  }, [documents, query])

  // The main library is verified-only by construction — demo records only
  // ever appear in the separate advanced panel below, never mixed in here.
  const verified = useMemo(() => searched.filter((s) => s.is_verified), [searched])
  const demo = useMemo(() => searched.filter((s) => s.is_mock), [searched])

  const sections = useMemo(
    () =>
      GROUPS.filter((g) => filter === 'verified' || filter === 'all' || filter === g.key)
        .map((group) => ({ group, items: verified.filter(group.matches) }))
        .filter((section) => section.items.length > 0),
    [verified, filter],
  )

  const demoSections = useMemo(
    () => GROUPS.map((group) => ({ group, items: demo.filter(group.matches) })).filter((s) => s.items.length > 0),
    [demo],
  )

  return (
    <div className="mx-auto max-w-5xl px-4 py-12 sm:px-6">
      <div className="flex items-center gap-2.5">
        <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand-50 text-brand-600">
          <Library className="h-4.5 w-4.5" />
        </span>
        <span className="section-title">Standards &amp; Regulatory Library</span>
      </div>

      <h1 className="mt-4 text-3xl font-extrabold tracking-tight text-ink-900">
        Standards &amp; Regulatory Library
      </h1>
      <p className="mt-2 max-w-2xl text-sm leading-relaxed text-ink-500">
        Browse the verified standards-related documents and regulatory sources used by the
        platform.
      </p>

      <div className="relative mt-6 max-w-md">
        <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-400" />
        <input
          className="field pl-10"
          placeholder="Search by IS number, product or keyword"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>

      <div className="mt-4 flex flex-wrap gap-1.5">
        {FILTER_CHIPS.map((chip) => (
          <button
            key={chip.key}
            onClick={() => setFilter(chip.key)}
            className={`rounded-lg border px-3 py-1.5 text-xs font-semibold transition-colors ${
              filter === chip.key
                ? 'border-brand-500 bg-brand-600 text-white'
                : 'border-ink-200 bg-white text-ink-600 hover:border-brand-300 hover:bg-brand-50'
            }`}
          >
            {chip.label}
          </button>
        ))}
      </div>

      {loading && (
        <div className="mt-6">
          <LoadingSkeleton rows={3} />
        </div>
      )}
      {error && (
        <div className="mt-6">
          <ErrorState message={error} />
        </div>
      )}

      {!loading && !error && sections.length === 0 && (
        <p className="mt-8 text-sm text-ink-500">
          No verified document matches. Try a different search or filter, or view the demo corpus
          below.
        </p>
      )}

      <div className="mt-8 space-y-10">
        {sections.map(({ group, items }) => (
          <section key={group.key}>
            <div className="border-b-2 border-ink-900 pb-2">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <h2 className="text-xl font-extrabold tracking-tight text-ink-900">{group.label}</h2>
                <span className="text-xs font-semibold text-ink-400">
                  {items.length} document{items.length === 1 ? '' : 's'}
                </span>
              </div>
              <p className="mt-1 max-w-2xl text-xs leading-relaxed text-ink-500">{group.blurb}</p>
            </div>
            <div className="mt-5 grid gap-3 sm:grid-cols-2">
              {items.map((doc) => (
                <DocumentCard key={doc.id} doc={doc} />
              ))}
            </div>
          </section>
        ))}
      </div>

      {/* Advanced: demo corpus, kept clearly separate from verified sections */}
      {demo.length > 0 && (
        <div className="mt-12 border-t border-ink-200 pt-6">
          <button
            className="btn-secondary btn-sm"
            onClick={() => setShowDemo((v) => !v)}
            aria-expanded={showDemo}
          >
            <Layers className="h-3.5 w-3.5" />
            {showDemo ? 'Hide' : 'View'} demo corpus
            <ChevronDown className={`h-3.5 w-3.5 transition-transform ${showDemo ? 'rotate-180' : ''}`} />
          </button>
          {showDemo && (
            <div className="mt-5 space-y-8">
              <p className="max-w-2xl text-xs leading-relaxed text-ink-500">
                A synthetic demonstration dataset, kept separate from verified official sources.
                Every record here is labelled Demo Data.
              </p>
              {demoSections.map(({ group, items }) => (
                <section key={group.key}>
                  <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-ink-200 pb-1.5">
                    <h3 className="text-sm font-bold text-ink-700">{group.label}</h3>
                    <span className="text-xs font-semibold text-ink-400">
                      {items.length} document{items.length === 1 ? '' : 's'}
                    </span>
                  </div>
                  <div className="mt-3 grid gap-3 sm:grid-cols-2">
                    {items.map((doc) => (
                      <DocumentCard key={doc.id} doc={doc} />
                    ))}
                  </div>
                </section>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function DocumentCard({ doc }: { doc: StandardSummary }) {
  const kind = documentTypeMeta(doc.document_type)
  const isTestMethod = doc.document_type === 'standard' && doc.product_category === 'test-method'
  return (
    <Link to={`/standards/${doc.id}`} className="card card-hover p-4">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="rounded bg-ink-900 px-2 py-0.5 font-mono text-[11px] font-bold text-white">
          {doc.display_number}
        </span>
        <span className={`chip ${kind.chip}`} title={kind.description}>
          {isTestMethod ? 'Test Method' : kind.label}
        </span>
        {doc.is_verified ? (
          <span
            className="chip bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200"
            title={doc.source_url ? `Official source: ${doc.source_url}` : 'Official source document'}
          >
            <ShieldCheck className="h-3 w-3" />
            Verified Official Source
          </span>
        ) : (
          doc.is_mock && <DemoDataBadge compact />
        )}
      </div>

      <h3 className="mt-2 text-sm font-bold leading-snug text-ink-900">{doc.title}</h3>

      {doc.is_verified && doc.retrieved_at && (
        <p className="mt-1.5 font-mono text-[10px] text-ink-400">
          Retrieved {doc.retrieved_at} from bis.gov.in
        </p>
      )}
    </Link>
  )
}

// ---------------------------------------------------------------------------
// Standard / document detail (progressive disclosure)
// ---------------------------------------------------------------------------

/** Split curated summary text into a short, honest bullet list. Never applied
 *  to raw scope text, which for several verified sources is messy front-page
 *  boilerplate extracted from the source PDF — showing that as bullets would
 *  look invented even though it is technically sourced. */
function coverageBullets(text: string): string[] {
  return text
    .split(/(?<=[.!?])\s+/)
    .map((s) => s.trim())
    .filter((s) => s.length > 12)
    .slice(0, 5)
}

export function StandardDetailPage() {
  const { standardId = '' } = useParams()
  const drawer = useEvidenceDrawer()
  const [detail, setDetail] = useState<StandardDetail | null>(null)
  const [findings, setFindings] = useState<PlainFinding[]>([])
  const [findingsNote, setFindingsNote] = useState('')
  const [requirements, setRequirements] = useState<StandardRequirement[]>([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [regulatoryOpen, setRegulatoryOpen] = useState(false)
  const [showClauses, setShowClauses] = useState(false)
  const [showTechnical, setShowTechnical] = useState(false)
  const [openCategory, setOpenCategory] = useState<string | null>(null)
  const [openRelated, setOpenRelated] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setError('')
    api
      .getStandard(standardId)
      .then(setDetail)
      .catch((e) => setError(apiError(e)))
      .finally(() => setLoading(false))
    api
      .standardFindings(standardId)
      .then((r) => {
        setFindings(r.findings)
        setFindingsNote(r.note)
      })
      .catch(() => undefined)
    api
      .standardRequirements(standardId)
      .then((r) => setRequirements(r.requirements))
      .catch(() => undefined)
  }, [standardId])

  if (loading) {
    return (
      <div className="mx-auto max-w-4xl px-4 py-12 sm:px-6">
        <LoadingSkeleton rows={3} />
      </div>
    )
  }
  if (error || !detail) {
    return (
      <div className="mx-auto max-w-4xl px-4 py-12 sm:px-6">
        <ErrorState message={error || 'Standard not found.'} />
      </div>
    )
  }

  const kind = documentTypeMeta(detail.standard.document_type)
  const bullets = detail.plain_summary ? coverageBullets(detail.plain_summary) : []
  const categories = Object.entries(detail.requirement_categories).sort((a, b) => a[0].localeCompare(b[0]))
  const requirementsByCategory = new Map<string, StandardRequirement[]>()
  requirements.forEach((r) => {
    requirementsByCategory.set(r.category, [...(requirementsByCategory.get(r.category) ?? []), r])
  })
  const grouped = detail.clauses.reduce<Record<string, typeof detail.clauses>>((acc, clause) => {
    const key = clause.clause_number.split('.')[0]
    acc[key] = [...(acc[key] ?? []), clause]
    return acc
  }, {})

  return (
    <div className="mx-auto max-w-4xl px-4 py-12 sm:px-6">
      <Link to="/standards" className="btn-ghost btn-sm -ml-3">
        <ArrowLeft className="h-3.5 w-3.5" />
        Standards library
      </Link>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <span className="rounded-lg bg-ink-900 px-2.5 py-1 font-mono text-sm font-bold text-white">
          {detail.standard.display_number}
        </span>
        <span className={`chip ${kind.chip}`} title={kind.description}>
          {kind.label}
        </span>
        <RegulatoryBadge status={detail.regulatory.status} verified={detail.regulatory.verified} />
        {detail.standard.is_verified ? (
          <span className="chip bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200">
            <ShieldCheck className="h-3.5 w-3.5" />
            Verified Official Source
          </span>
        ) : (
          detail.standard.is_mock && <DemoDataBadge />
        )}
      </div>

      <h1 className="mt-3 text-3xl font-extrabold leading-tight tracking-tight text-ink-900">
        {detail.standard.title}
      </h1>

      <p className="mt-2 text-xs leading-relaxed text-ink-500">{kind.description}</p>

      {detail.standard.is_verified && detail.standard.source_url && (
        <p className="mt-1.5 text-xs text-ink-500">
          Official source:{' '}
          <a className="link" href={detail.standard.source_url} target="_blank" rel="noreferrer">
            bis.gov.in
          </a>
          {detail.standard.retrieved_at ? ` · retrieved ${detail.standard.retrieved_at}` : ''}
        </p>
      )}

      {detail.plain_summary && (
        <p className="mt-3 max-w-3xl text-base leading-relaxed text-ink-600">{detail.plain_summary}</p>
      )}

      <p className="mt-4 text-xs font-medium text-ink-400">
        {detail.standard.clause_count} clause{detail.standard.clause_count === 1 ? '' : 's'} ·{' '}
        {detail.standard.requirement_count} requirement{detail.standard.requirement_count === 1 ? '' : 's'} ·{' '}
        {detail.amendments.length} amendment{detail.amendments.length === 1 ? '' : 's'}
      </p>

      {/* WHAT THIS COVERS */}
      {bullets.length > 0 && (
        <section className="mt-8">
          <SectionHeading title="What this covers" />
          <ul className="space-y-1.5">
            {bullets.map((b, i) => (
              <li key={i} className="flex items-start gap-2 text-sm leading-relaxed text-ink-700">
                <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-500" />
                {b}
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* MAIN REQUIREMENTS */}
      {categories.length > 0 && (
        <section className="mt-8">
          <SectionHeading
            title="Main requirements"
            description="Grouped from structured requirements extracted for this document."
          />
          <div className="space-y-2">
            {categories.map(([category, count]) => {
              const open = openCategory === category
              const items = requirementsByCategory.get(category) ?? []
              return (
                <div key={category} className="overflow-hidden rounded-xl border border-ink-200">
                  <button
                    type="button"
                    className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left transition-colors hover:bg-ink-50/60"
                    onClick={() => setOpenCategory(open ? null : category)}
                    aria-expanded={open}
                  >
                    <span className="text-sm font-semibold text-ink-800">
                      {CATEGORY_LABELS[category] ?? titleCase(category)}
                    </span>
                    <span className="flex items-center gap-2 text-xs text-ink-500">
                      {count} requirement{count === 1 ? '' : 's'}
                      <ChevronDown className={`h-3.5 w-3.5 transition-transform ${open ? 'rotate-180' : ''}`} />
                    </span>
                  </button>
                  {open && (
                    <ul className="space-y-2 border-t border-ink-100 bg-ink-50/40 px-4 py-3">
                      {items.length > 0 ? (
                        items.map((r) => (
                          <li key={r.id} className="text-sm leading-relaxed text-ink-700">
                            <span className="mr-1.5 rounded bg-ink-100 px-1.5 py-0.5 font-mono text-[10px] font-bold text-ink-500">
                              {r.requirement_code}
                            </span>
                            {r.requirement_text}
                            {r.source_clause_number && (
                              <span className="ml-1.5 text-xs text-ink-400">
                                (Clause {r.source_clause_number})
                              </span>
                            )}
                          </li>
                        ))
                      ) : (
                        <li className="text-xs text-ink-400">Loading…</li>
                      )}
                    </ul>
                  )}
                </div>
              )
            })}
          </div>
        </section>
      )}

      {/* WHAT YOU NEED TO KNOW */}
      {findings.length > 0 && (
        <section className="mt-8">
          <SectionHeading
            title="What you need to know"
            description="Read from the source document itself — each point links to the exact clause it came from."
          />
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
        </section>
      )}
      {findings.length === 0 && findingsNote && (
        <section className="mt-8">
          <SectionHeading title="What you need to know" />
          <p className="text-sm leading-relaxed text-ink-500">{findingsNote}</p>
        </section>
      )}

      {/* REGULATORY STATUS */}
      <section className="mt-8">
        <SectionHeading title="Regulatory status" />
        <RegulatoryCard
          regulatory={detail.regulatory}
          standardId={detail.regulatory.status !== 'UNABLE_TO_VERIFY' ? standardId : null}
          onView={() => setRegulatoryOpen(true)}
        />
      </section>

      {/* RELATED STANDARDS */}
      {detail.related.length > 0 && (
        <section className="mt-8">
          <SectionHeading
            title="Related standards"
            description="Derived from normative references stated in the document."
          />
          <div className="space-y-2">
            {detail.related.map((rel) => {
              const key = `${rel.standard_id}-${rel.relationship_type}`
              const open = openRelated === key
              return (
                <div key={key} className="card overflow-hidden p-0">
                  <div className="flex items-start justify-between gap-3 p-4">
                    <Link to={`/standards/${rel.standard_id}`} className="flex min-w-0 items-start gap-3">
                      <BookMarked className="mt-0.5 h-4 w-4 shrink-0 text-brand-500" />
                      <div className="min-w-0">
                        <div className="text-sm font-bold text-ink-900">
                          {rel.is_number} — {rel.title}
                        </div>
                        <div className="text-xs text-ink-400">{titleCase(rel.relationship_type)}</div>
                      </div>
                    </Link>
                    {rel.evidence && (
                      <button
                        className="btn-ghost btn-sm shrink-0"
                        onClick={() => setOpenRelated(open ? null : key)}
                      >
                        {open ? 'Hide' : 'Why?'}
                      </button>
                    )}
                  </div>
                  {open && rel.evidence && (
                    <p className="border-t border-ink-100 bg-ink-50/50 px-4 py-3 text-xs leading-relaxed text-ink-500">
                      {rel.evidence}
                    </p>
                  )}
                </div>
              )
            })}
          </div>
        </section>
      )}

      {/* SOURCE EVIDENCE */}
      <section className="mt-8">
        <SectionHeading title="Source evidence" />
        <div className="card p-4">
          <p className="text-sm leading-relaxed text-ink-600">
            Exact clauses, page references and source text are available for verification.
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            <button className="btn-secondary btn-sm" onClick={() => setShowClauses((v) => !v)}>
              <FileSearch className="h-3.5 w-3.5" />
              {showClauses ? 'Hide' : 'View'} source clauses
            </button>
            {detail.standard.source_url && (
              <a
                className="btn-ghost btn-sm"
                href={detail.standard.source_url}
                target="_blank"
                rel="noreferrer"
              >
                <ExternalLink className="h-3.5 w-3.5" />
                Open official source
              </a>
            )}
          </div>
        </div>

        {showClauses && (
          <div className="mt-4 space-y-5">
            {Object.entries(grouped)
              .sort((a, b) => Number(a[0]) - Number(b[0]))
              .map(([section, clauses]) => (
                <div key={section} className="card overflow-hidden">
                  <div className="border-b border-ink-200 bg-ink-50/70 px-4 py-2.5">
                    <span className="text-sm font-bold text-ink-800">
                      Section {section}
                      {clauses[0]?.heading ? ` — ${clauses[0].heading.split(' > ')[0]}` : ''}
                    </span>
                  </div>
                  <ul className="divide-y divide-ink-100">
                    {clauses.map((clause) => (
                      <li key={clause.chunk_id} className="px-4 py-3">
                        <button className="text-left" onClick={() => drawer.open(clause.chunk_id)}>
                          <span className="font-mono text-xs font-bold text-brand-700">
                            {clause.clause_number}
                          </span>
                          <span className="ml-2 text-xs uppercase tracking-wide text-ink-400">
                            {clause.clause_type}
                          </span>
                          {clause.page_number && clause.page_number > 0 && (
                            <span className="ml-2 text-xs text-ink-400">Page {clause.page_number}</span>
                          )}
                          <p className="mt-1 text-sm leading-relaxed text-ink-700">{clause.excerpt}</p>
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
          </div>
        )}
      </section>

      {/* TECHNICAL DETAILS */}
      <section className="mt-8">
        <button
          className="btn-ghost btn-sm"
          onClick={() => setShowTechnical((v) => !v)}
          aria-expanded={showTechnical}
        >
          <ChevronDown className={`h-3.5 w-3.5 transition-transform ${showTechnical ? 'rotate-180' : ''}`} />
          {showTechnical ? 'Hide' : 'View'} technical details
        </button>

        {showTechnical && (
          <div className="mt-4 space-y-5">
            <div className="card p-4">
              <div className="section-title mb-2">Provenance</div>
              <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs">
                <TechRow label="Document type" value={detail.standard.document_type} />
                <TechRow label="Source type" value={detail.standard.source_type} />
                <TechRow label="Verified" value={detail.standard.is_verified ? 'Yes' : 'No'} />
                <TechRow label="Demo dataset" value={detail.standard.is_mock ? 'Yes' : 'No'} />
                <TechRow label="Version" value={detail.standard.version} />
                <TechRow label="Year" value={detail.standard.year ? String(detail.standard.year) : null} />
                <TechRow label="Category" value={detail.standard.product_category ? titleCase(detail.standard.product_category) : null} />
                <TechRow label="Retrieved" value={detail.standard.retrieved_at} />
              </dl>
            </div>

            {detail.amendments.length > 0 && (
              <div className="card p-4">
                <div className="section-title mb-2">Amendments</div>
                <ul className="space-y-2">
                  {detail.amendments.map((a) => (
                    <li key={a.id} className="text-xs leading-relaxed text-ink-600">
                      <span className="font-mono font-bold text-ink-800">{a.amendment_number}</span>{' '}
                      — clause {a.affected_clause}
                      {a.effective_date ? ` · effective ${a.effective_date}` : ''}
                      {a.summary ? `: ${a.summary}` : ''}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {requirements.length > 0 && (
              <div className="card p-4">
                <div className="section-title mb-2">Requirement IDs</div>
                <div className="flex flex-wrap gap-1.5">
                  {requirements.map((r) => (
                    <span
                      key={r.id}
                      className="chip bg-ink-100 text-ink-600"
                      title={`${r.requirement_text} (severity: ${r.severity}, evidence: ${r.evidence_type.replace(/_/g, ' ')})`}
                    >
                      {r.requirement_code}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </section>

      <EvidenceDrawer chunkId={drawer.chunkId} onClose={drawer.close} onNavigate={drawer.open} />
      <RegulatoryDrawer standardId={regulatoryOpen ? standardId : null} onClose={() => setRegulatoryOpen(false)} />
    </div>
  )
}

function TechRow({ label, value }: { label: string; value: string | null }) {
  if (!value) return null
  return (
    <>
      <dt className="font-semibold text-ink-500">{label}</dt>
      <dd className="text-ink-800">{value}</dd>
    </>
  )
}
