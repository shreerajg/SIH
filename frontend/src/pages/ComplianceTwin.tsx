import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  Boxes,
  Download,
  FileText,
  FlaskConical,
  GitCompareArrows,
  Layers,
  Link2,
  Network,
  Paperclip,
  ScrollText,
  Share2,
} from 'lucide-react'
import { api, apiError } from '@/lib/api'
import type { ComplianceTwinResponse, TestPlanItem } from '@/lib/types'
import { attributeLabel, formatValue, STATUS_META, titleCase } from '@/lib/format'
import { RequirementTable } from '@/components/RequirementTable'
import { CategoryBreakdown, ReadinessMeter } from '@/components/ComplianceSummary'
import { StandardCard } from '@/components/StandardCard'
import { AmendmentPanel } from '@/components/AmendmentPanel'
import { KnowledgeGraph } from '@/components/KnowledgeGraph'
import { EvidenceCitation, EvidenceDrawer, useEvidenceDrawer } from '@/components/EvidenceDrawer'
import { RegulatoryDrawer } from '@/components/RegulatoryDrawer'
import {
  DisclaimerBanner,
  EmptyState,
  ErrorState,
  LoadingSkeleton,
  SectionHeading,
  Stat,
  StatusBadge,
} from '@/components/primitives'

const TABS = [
  { id: 'overview', label: 'Overview', icon: Boxes },
  { id: 'standards', label: 'Standards', icon: Layers },
  { id: 'requirements', label: 'Requirements', icon: ScrollText },
  { id: 'testing', label: 'Testing', icon: FlaskConical },
  { id: 'evidence', label: 'Evidence', icon: Paperclip },
  { id: 'gaps', label: 'Gaps', icon: Share2 },
  { id: 'amendments', label: 'Amendments', icon: GitCompareArrows },
  { id: 'graph', label: 'Graph', icon: Network },
  { id: 'sources', label: 'Sources', icon: FileText },
] as const

type TabId = (typeof TABS)[number]['id']

export function ComplianceTwin() {
  const { productId = '' } = useParams()
  const drawer = useEvidenceDrawer()
  const [data, setData] = useState<ComplianceTwinResponse | null>(null)
  const [tab, setTab] = useState<TabId>('overview')
  const [regulatoryFor, setRegulatoryFor] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  const load = useCallback(() => {
    setLoading(true)
    setError('')
    api
      .complianceTwin(productId)
      .then(setData)
      .catch((e) => setError(apiError(e)))
      .finally(() => setLoading(false))
  }, [productId])

  useEffect(load, [load])

  if (loading) {
    return (
      <div className="mx-auto max-w-7xl px-4 py-12 sm:px-6">
        <LoadingSkeleton rows={3} />
      </div>
    )
  }
  if (error) {
    return (
      <div className="mx-auto max-w-7xl px-4 py-12 sm:px-6">
        <ErrorState message={error} onRetry={load} />
      </div>
    )
  }
  if (!data) return null

  const s = data.summary
  const gaps = data.results.filter((r) =>
    ['POTENTIAL_GAP', 'TEST_REQUIRED', 'DOCUMENT_REQUIRED', 'UNKNOWN'].includes(r.status),
  )

  const openEvidence = (evidenceId: string) => {
    setTab('evidence')
    requestAnimationFrame(() => {
      document
        .getElementById(`evidence-${evidenceId}`)
        ?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    })
  }

  const downloadTestPlan = () => {
    const lines = data.testing_plan.map((item) => {
      const parts = [
        `[${item.status.replace(/_/g, ' ')}] ${item.requirement_code} — ${item.test}`,
        `  Standard: ${item.standard}, Clause ${item.clause}`,
      ]
      if (item.test_method_reference) {
        parts.push(
          `  Test procedure: see ${item.test_method_reference.standard} — ${item.test_method_reference.evidence}`,
        )
      }
      if (item.matched_evidence) {
        parts.push(`  Evidence on file: ${item.matched_evidence}`)
      }
      parts.push(`  Action: ${item.action}`)
      return parts.join('\n')
    })
    const header =
      `Compliance test plan — ${data.product.name}\n` +
      `Generated ${new Date().toLocaleString()}\n` +
      `${'-'.repeat(60)}\n` +
      `This is a pre-compliance preparation checklist, not a certification result.\n\n`
    const blob = new Blob([header + lines.join('\n\n')], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `test-plan-${productId}.txt`
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  }

  const outstandingTests = data.testing_plan.filter((t) => t.status !== 'SUPPORTED')
  const supportedTests = data.testing_plan.filter((t) => t.status === 'SUPPORTED')

  return (
    <div className="mx-auto max-w-7xl px-4 py-10 sm:px-6">
      {/* Header */}
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="section-title">Product Compliance Twin</div>
          <h1 className="mt-1.5 text-3xl font-extrabold tracking-tight text-ink-900 sm:text-4xl">
            {data.product.name}
          </h1>
          <p className="mt-1.5 max-w-2xl text-sm text-ink-500">{data.product.description}</p>
        </div>
        <div className="flex gap-2">
          <Link to={`/product/${productId}/gap-analysis`} className="btn-secondary btn-sm">
            Update evidence
          </Link>
          <Link to={`/assistant?product=${productId}`} className="btn-primary btn-sm">
            Ask a question
          </Link>
        </div>
      </div>

      {/* Summary strip */}
      <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <Stat label="Applicable standards" value={s.applicable_standards ?? 0} tone="brand" />
        <Stat label="Requirements identified" value={s.requirements_identified ?? 0} />
        <Stat label="Supported" value={s.supported ?? 0} tone="good" />
        <Stat label="Potential gaps" value={s.potential_gaps ?? 0} tone="bad" />
        <Stat label="Test evidence needed" value={s.test_evidence_required ?? 0} tone="warn" />
        <Stat label="Unknown" value={s.unknown ?? 0} tone="muted" />
      </div>

      {!data.analysis_available && (
        <div className="mt-6">
          <EmptyState
            title="No pre-compliance analysis yet"
            description="Standards have been matched, but requirements have not been assessed against your evidence. Run the gap analyzer to populate this dashboard."
            action={
              <Link to={`/product/${productId}/gap-analysis`} className="btn-primary btn-sm">
                Run pre-compliance analysis
              </Link>
            }
          />
        </div>
      )}

      {/* Tabs */}
      <div className="mt-8 border-b border-ink-200">
        <nav className="scroll-thin -mb-px flex gap-1 overflow-x-auto">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`flex shrink-0 items-center gap-1.5 border-b-2 px-3.5 py-2.5 text-sm font-semibold transition-colors ${
                tab === t.id
                  ? 'border-brand-600 text-brand-700'
                  : 'border-transparent text-ink-500 hover:border-ink-300 hover:text-ink-800'
              }`}
            >
              <t.icon className="h-4 w-4" />
              {t.label}
            </button>
          ))}
        </nav>
      </div>

      <div className="mt-6">
        {tab === 'overview' && (
          <div className="grid gap-5 lg:grid-cols-[1.4fr_1fr]">
            <div className="space-y-5">
              <ReadinessMeter readiness={data.readiness} />
              <CategoryBreakdown readiness={data.readiness} />
            </div>
            <div className="space-y-5">
              <section className="card p-5">
                <SectionHeading title="Product profile" />
                <dl className="space-y-2.5">
                  <div className="flex items-baseline justify-between gap-4 text-sm">
                    <dt className="text-ink-500">Category</dt>
                    <dd className="font-semibold text-ink-900">
                      {data.product.category ? titleCase(data.product.category) : '—'}
                    </dd>
                  </div>
                  {Object.entries(data.product.attributes).map(([k, v]) => (
                    <div key={k} className="flex items-baseline justify-between gap-4 text-sm">
                      <dt className="text-ink-500">{attributeLabel(k)}</dt>
                      <dd className="text-right font-semibold text-ink-900">{formatValue(v)}</dd>
                    </div>
                  ))}
                </dl>
              </section>

              <section className="card p-5">
                <SectionHeading title="Regulatory position" />
                <div className="space-y-2 text-sm">
                  <div className="flex items-baseline justify-between">
                    <span className="text-ink-500">Standards with a mandatory record</span>
                    <span className="font-bold text-rose-600">{s.mandatory_standards ?? 0}</span>
                  </div>
                  <div className="flex items-baseline justify-between">
                    <span className="text-ink-500">Regulatory status unverifiable</span>
                    <span className="font-bold text-ink-500">{s.unverified_regulatory ?? 0}</span>
                  </div>
                  <div className="flex items-baseline justify-between">
                    <span className="text-ink-500">Amendment alerts</span>
                    <span className="font-bold text-amber-600">{s.amendment_alerts ?? 0}</span>
                  </div>
                </div>
                <p className="mt-3 text-xs leading-relaxed text-ink-400">
                  Regulatory status is read from structured records only. Where no record exists the
                  platform reports &ldquo;unable to verify&rdquo; rather than inferring that a
                  standard is voluntary.
                </p>
              </section>
            </div>
          </div>
        )}

        {tab === 'standards' && (
          <div className="space-y-4">
            {data.standards.map((match) => (
              <StandardCard
                key={match.standard.id}
                match={match}
                onOpenSource={drawer.open}
                onViewRegulatory={setRegulatoryFor}
              />
            ))}
          </div>
        )}

        {tab === 'requirements' && (
          <RequirementTable results={data.results} onOpenSource={drawer.open} />
        )}

        {tab === 'testing' && (
          <section>
            <SectionHeading
              title="Compliance test plan"
              description="Every requirement whose evidence type is a test report, grouped by what is still outstanding."
              action={
                data.testing_plan.length > 0 && (
                  <button className="btn-secondary btn-sm" onClick={downloadTestPlan}>
                    <Download className="h-3.5 w-3.5" />
                    Download checklist
                  </button>
                )
              }
            />
            {data.testing_plan.length === 0 ? (
              <EmptyState
                title="No test requirements identified"
                description="Run the pre-compliance analysis to build the test plan."
              />
            ) : (
              <div className="space-y-6">
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                  <Stat label="Total tests" value={data.testing_plan.length} />
                  <Stat label="Outstanding" value={outstandingTests.length} tone="warn" />
                  <Stat label="On file" value={supportedTests.length} tone="good" />
                </div>

                {outstandingTests.length > 0 && (
                  <TestPlanTable
                    title="Outstanding"
                    items={outstandingTests}
                    onOpenSource={drawer.open}
                    onOpenEvidence={openEvidence}
                  />
                )}
                {supportedTests.length > 0 && (
                  <TestPlanTable
                    title="On file"
                    items={supportedTests}
                    onOpenSource={drawer.open}
                    onOpenEvidence={openEvidence}
                  />
                )}
              </div>
            )}
          </section>
        )}

        {tab === 'evidence' && (
          <section>
            <SectionHeading
              title="Evidence on file"
              description="What the manufacturer has declared holding for this product."
            />
            {data.evidence.length === 0 ? (
              <EmptyState
                title="No evidence recorded"
                description="Open the gap analyzer and tick the reports, certificates and documents you hold."
                action={
                  <Link to={`/product/${productId}/gap-analysis`} className="btn-secondary btn-sm">
                    Add evidence
                  </Link>
                }
              />
            ) : (
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {data.evidence.map((item) => (
                  <div key={item.id} id={`evidence-${item.id}`} className="card scroll-mt-24 p-4">
                    <span className="chip bg-ink-100 text-ink-600">
                      {item.evidence_type.replace(/_/g, ' ')}
                    </span>
                    <h3 className="mt-2 text-sm font-semibold text-ink-900">{item.name}</h3>
                    {item.value && <p className="mt-1 text-xs text-ink-500">{item.value}</p>}
                  </div>
                ))}
              </div>
            )}
          </section>
        )}

        {tab === 'gaps' && (
          <section>
            <SectionHeading
              title="Outstanding items"
              description={`${gaps.length} requirement(s) need attention before a conformity assessment.`}
            />
            {gaps.length === 0 ? (
              <EmptyState
                title="Nothing outstanding in the current assessment"
                description="Every assessable requirement has supporting information on file. This is a preparation indicator, not a certification result."
              />
            ) : (
              <div className="space-y-3">
                {gaps.map((r) => (
                  <article key={r.requirement_id} className="card p-5">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <StatusBadge status={r.status} />
                          <span className="chip bg-ink-100 text-ink-600">{titleCase(r.category)}</span>
                          <span className="text-xs font-semibold uppercase tracking-wide text-ink-400">
                            {r.severity}
                          </span>
                        </div>
                        <h3 className="mt-2.5 text-sm font-semibold leading-relaxed text-ink-900">
                          {r.requirement_text}
                        </h3>
                        <p className="mt-1.5 text-sm leading-relaxed text-ink-600">{r.reason}</p>
                        {r.recommended_action && (
                          <p
                            className={`mt-2.5 rounded-lg px-3 py-2 text-sm leading-relaxed ${
                              STATUS_META[r.status].chip
                            }`}
                          >
                            <span className="font-semibold">Next: </span>
                            {r.recommended_action}
                          </p>
                        )}
                      </div>
                      <EvidenceCitation citation={r.source} onOpen={drawer.open} />
                    </div>
                  </article>
                ))}
              </div>
            )}
          </section>
        )}

        {tab === 'amendments' && <AmendmentPanel impacts={data.amendments} />}

        {tab === 'graph' && (
          <section>
            <SectionHeading
              title="Standards knowledge graph"
              description="Product to standards to regulatory records. Every edge comes from a stored record."
            />
            <KnowledgeGraph nodes={data.graph.nodes} edges={data.graph.edges} />
          </section>
        )}

        {tab === 'sources' && (
          <section>
            <SectionHeading
              title="All cited sources"
              description={`${data.sources.length} distinct clauses back the content of this dashboard.`}
            />
            <div className="space-y-2">
              {data.sources.map((source) => (
                <button
                  key={source.chunk_id}
                  onClick={() => drawer.open(source.chunk_id)}
                  className="card card-hover w-full p-4 text-left"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="rounded bg-ink-900 px-2 py-0.5 font-mono text-[11px] font-bold text-white">
                      {source.display_number}
                    </span>
                    <span className="text-xs font-semibold text-ink-600">
                      Clause {source.clause_number}
                    </span>
                    {source.heading && (
                      <span className="text-xs text-ink-400">{source.heading}</span>
                    )}
                  </div>
                  <p className="mt-1.5 line-clamp-2 text-sm leading-relaxed text-ink-600">
                    {source.excerpt}
                  </p>
                </button>
              ))}
            </div>
          </section>
        )}
      </div>

      <div className="mt-10">
        <DisclaimerBanner text={data.disclaimer} />
      </div>

      <EvidenceDrawer chunkId={drawer.chunkId} onClose={drawer.close} onNavigate={drawer.open} />
      <RegulatoryDrawer standardId={regulatoryFor} onClose={() => setRegulatoryFor(null)} />
    </div>
  )
}

function TestPlanTable({
  title,
  items,
  onOpenSource,
  onOpenEvidence,
}: {
  title: string
  items: TestPlanItem[]
  onOpenSource: (chunkId: string) => void
  onOpenEvidence: (evidenceId: string) => void
}) {
  return (
    <div>
      <div className="mb-2 text-xs font-bold uppercase tracking-wide text-ink-400">
        {title} · {items.length}
      </div>
      <div className="card overflow-hidden">
        <div className="scroll-thin overflow-x-auto">
          <table className="w-full min-w-[900px] text-left text-sm">
            <thead className="border-b border-ink-200 bg-ink-50/70 text-xs font-semibold uppercase tracking-wide text-ink-500">
              <tr>
                <th className="px-4 py-3">Test</th>
                <th className="px-3 py-3 w-40">Status</th>
                <th className="px-3 py-3 w-40">Source</th>
                <th className="px-3 py-3 w-52">Test procedure</th>
                <th className="px-3 py-3 w-64">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-100">
              {items.map((item) => (
                <tr key={item.requirement_code} className="align-top">
                  <td className="px-4 py-3.5">
                    <span className="mr-2 rounded bg-ink-100 px-1.5 py-0.5 font-mono text-[10px] font-bold text-ink-500">
                      {item.requirement_code}
                    </span>
                    <span className="text-ink-800">{item.test}</span>
                    {item.matched_evidence && (
                      <button
                        className="mt-1.5 flex items-center gap-1 text-xs font-medium text-brand-700 hover:underline"
                        onClick={() => item.evidence_id && onOpenEvidence(item.evidence_id)}
                        disabled={!item.evidence_id}
                      >
                        <Link2 className="h-3 w-3" />
                        {item.matched_evidence}
                      </button>
                    )}
                  </td>
                  <td className="px-3 py-3.5">
                    <StatusBadge status={item.status} />
                  </td>
                  <td className="px-3 py-3.5">
                    <EvidenceCitation
                      citation={{
                        chunk_id: item.chunk_id,
                        display_number: item.standard,
                        clause_number: item.clause,
                        page_number: null,
                      }}
                      onOpen={onOpenSource}
                    />
                  </td>
                  <td className="px-3 py-3.5 text-xs leading-relaxed text-ink-600">
                    {item.test_method_reference ? (
                      <span title={item.test_method_reference.evidence}>
                        Per{' '}
                        <span className="font-mono font-semibold text-ink-800">
                          {item.test_method_reference.standard}
                        </span>
                      </span>
                    ) : (
                      <span className="text-ink-300">—</span>
                    )}
                  </td>
                  <td className="px-3 py-3.5 text-xs leading-relaxed text-ink-600">
                    {item.action}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
