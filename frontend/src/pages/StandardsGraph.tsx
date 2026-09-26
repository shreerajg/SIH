import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Crosshair,
  ExternalLink,
  Layers,
  Network,
  Package,
  ShieldCheck,
  Workflow,
} from 'lucide-react'
import { api, apiError } from '@/lib/api'
import type {
  GraphEdge,
  GraphNode,
  RegulatoryStatusValue,
  StandardsGraphResponse,
} from '@/lib/types'
import { titleCase } from '@/lib/format'
import { CorpusGraph } from '@/components/CorpusGraph'
import { ProductGraph } from '@/components/ProductGraph'
import {
  DemoDataBadge,
  DisclaimerBanner,
  EmptyState,
  ErrorState,
  LoadingSkeleton,
  RegulatoryBadge,
  SectionHeading,
  Stat,
} from '@/components/primitives'

/** Categories that are documents *about* regulation or test methods, not the
 *  product standards a manufacturer would pick as a starting point. */
const NON_PRODUCT_CATEGORIES = new Set(['regulatory-order', 'test-method'])

type ProductOption = {
  standardId: string
  display: string
  name: string
  category: string
}

/** A short, human product name taken from the standard's own title — never
 *  invented. Strips the "Product Manual:" prefix and the trailing document code. */
function friendlyProductName(title: string | undefined, fallback: string): string {
  let t = (title || '').trim()
  t = t.replace(/^product manual\s*:?\s*/i, '')
  t = t.replace(/\s*\([^)]*\)\s*$/, '')
  t = t.trim()
  return t || fallback
}

/** Build the product picker from the verified product standards in the corpus. */
function toProductOptions(full: StandardsGraphResponse | null): ProductOption[] {
  if (!full) return []
  return full.nodes
    .filter(
      (n) =>
        n.type === 'standard' &&
        !n.is_demo &&
        n.standard_id &&
        n.category &&
        !NON_PRODUCT_CATEGORIES.has(n.category),
    )
    .map((n) => ({
      standardId: n.standard_id as string,
      display: n.label,
      name: friendlyProductName(n.title, n.label),
      category: n.category as string,
    }))
}

/** Slice the corpus graph down to one standard's verified neighbourhood, then
 *  prepend the chosen product as an explicit, dashed context node. Every other
 *  node and edge is a stored record; demonstration records are left out. */
function buildProductSubgraph(
  full: StandardsGraphResponse,
  option: ProductOption,
): { nodes: GraphNode[]; edges: GraphEdge[] } {
  const rootId = `standard:${option.standardId}`
  const keep = new Set<string>([rootId])
  full.edges.forEach((e) => {
    if (e.is_demo) return
    if (e.source === rootId) keep.add(e.target)
    if (e.target === rootId) keep.add(e.source)
  })

  const nodes = full.nodes.filter((n) => keep.has(n.id) && !n.is_demo)
  const edges = full.edges.filter(
    (e) => keep.has(e.source) && keep.has(e.target) && !e.is_demo,
  )

  const productNode: GraphNode = {
    id: `product:${option.standardId}`,
    type: 'product',
    label: option.name,
    title: `${option.name} — the product you are exploring`,
  }
  const productEdge: GraphEdge = {
    source: productNode.id,
    target: rootId,
    type: 'covered_by',
    label: 'covered by',
    evidence: `${option.name} is covered by ${option.display}, the BIS product standard for this product.`,
  }

  return { nodes: [productNode, ...nodes], edges: [productEdge, ...edges] }
}

export function StandardsGraph() {
  const [mode, setMode] = useState<'product' | 'advanced'>('product')

  // Product view: one corpus fetch, sliced per selected product.
  const [full, setFull] = useState<StandardsGraphResponse | null>(null)
  const [product, setProduct] = useState('')
  const [selected, setSelected] = useState<GraphNode | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  const loadFull = useCallback(() => {
    setLoading(true)
    setError('')
    api
      .standardsGraph({ regulatory: true })
      .then((d) => setFull(d))
      .catch((e) => setError(apiError(e)))
      .finally(() => setLoading(false))
  }, [])

  useEffect(loadFull, [loadFull])

  const productOptions = useMemo(() => toProductOptions(full), [full])

  // Pick a sensible default the first time options arrive.
  useEffect(() => {
    if (product || productOptions.length === 0) return
    const preferred =
      productOptions.find((o) => /pressure cooker/i.test(o.name)) ?? productOptions[0]
    setProduct(preferred.standardId)
  }, [productOptions, product])

  const activeOption = useMemo(
    () => productOptions.find((o) => o.standardId === product) ?? null,
    [productOptions, product],
  )

  const subgraph = useMemo(
    () => (full && activeOption ? buildProductSubgraph(full, activeOption) : null),
    [full, activeOption],
  )

  const summary = useMemo(() => {
    if (!subgraph) return null
    return {
      sources: subgraph.nodes.filter((n) => n.type === 'standard').length,
      regulatory: subgraph.nodes.filter((n) => n.type === 'qco').length,
      relationships: subgraph.edges.filter((e) => e.type !== 'covered_by').length,
    }
  }, [subgraph])

  const selectProduct = (id: string) => {
    setProduct(id)
    setSelected(null)
  }

  return (
    <div className="mx-auto max-w-6xl px-4 py-12 sm:px-6">
      <div className="flex items-center gap-2.5">
        <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand-50 text-brand-600">
          <Network className="h-4.5 w-4.5" />
        </span>
        <span className="section-title">Knowledge graph</span>
      </div>

      <div className="mt-4 flex flex-wrap items-end justify-between gap-4">
        <div className="max-w-3xl">
          <h1 className="text-3xl font-extrabold tracking-tight text-ink-900">
            {mode === 'product' ? 'How a product connects to its standards' : 'Full corpus knowledge graph'}
          </h1>
          <p className="mt-2 text-sm leading-relaxed text-ink-500">
            {mode === 'product'
              ? 'Pick a product to see the BIS standard that covers it and the Quality Control Order that makes it mandatory. Every link is a stored record — nothing here is inferred by a language model.'
              : 'Every standard in the corpus and how they relate — normative references, test-method and marking standards, companion parts and the Quality Control Orders that make them mandatory. Includes demonstration records.'}
          </p>
        </div>
        <button
          className="btn-secondary btn-sm shrink-0"
          onClick={() => {
            setMode((m) => (m === 'product' ? 'advanced' : 'product'))
            setSelected(null)
          }}
        >
          {mode === 'product' ? (
            <>
              <Layers className="h-3.5 w-3.5" />
              View full corpus graph
            </>
          ) : (
            <>
              <Package className="h-3.5 w-3.5" />
              Back to product view
            </>
          )}
        </button>
      </div>

      {loading && (
        <div className="mt-6">
          <LoadingSkeleton rows={2} />
        </div>
      )}
      {error && (
        <div className="mt-6">
          <ErrorState message={error} onRetry={loadFull} />
        </div>
      )}

      {!loading && !error && full && mode === 'product' && (
        <ProductView
          options={productOptions}
          activeId={product}
          onSelectProduct={selectProduct}
          subgraph={subgraph}
          summary={summary}
          selected={selected}
          onSelectNode={setSelected}
          onOpenAdvanced={() => setMode('advanced')}
        />
      )}

      {!loading && !error && mode === 'advanced' && <AdvancedView />}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Product view
// ---------------------------------------------------------------------------

function ProductView({
  options,
  activeId,
  onSelectProduct,
  subgraph,
  summary,
  selected,
  onSelectNode,
  onOpenAdvanced,
}: {
  options: ProductOption[]
  activeId: string
  onSelectProduct: (id: string) => void
  subgraph: { nodes: GraphNode[]; edges: GraphEdge[] } | null
  summary: { sources: number; regulatory: number; relationships: number } | null
  selected: GraphNode | null
  onSelectNode: (node: GraphNode | null) => void
  onOpenAdvanced: () => void
}) {
  if (options.length === 0) {
    return (
      <div className="mt-6">
        <EmptyState
          icon={<Workflow className="h-5 w-5" />}
          title="No verified product standards loaded"
          description="The current corpus has no verified product standards to explore by product. You can still browse everything that is loaded in the full corpus graph."
          action={
            <button className="btn-secondary btn-sm" onClick={onOpenAdvanced}>
              <Layers className="h-3.5 w-3.5" />
              View full corpus graph
            </button>
          }
        />
      </div>
    )
  }

  return (
    <>
      {/* Product picker */}
      <div className="mt-6">
        <div className="section-title mb-2">Choose a product</div>
        <div className="flex flex-wrap gap-2">
          {options.map((o) => {
            const active = o.standardId === activeId
            return (
              <button
                key={o.standardId}
                onClick={() => onSelectProduct(o.standardId)}
                className={`rounded-xl border px-3.5 py-2 text-left transition-colors ${
                  active
                    ? 'border-brand-400 bg-brand-50 ring-1 ring-brand-200'
                    : 'border-ink-200 bg-white hover:border-brand-300 hover:bg-brand-50/40'
                }`}
              >
                <div className={`text-sm font-semibold ${active ? 'text-brand-900' : 'text-ink-800'}`}>
                  {o.name}
                </div>
                <div className="mt-0.5 font-mono text-[11px] text-ink-400">{o.display}</div>
              </button>
            )
          })}
        </div>
      </div>

      {summary && (
        <div className="mt-5 flex flex-wrap gap-2 text-xs">
          <SummaryChip label={summary.sources === 1 ? 'connected source' : 'connected sources'} value={summary.sources} tone="brand" />
          <SummaryChip label={summary.regulatory === 1 ? 'regulatory record' : 'regulatory records'} value={summary.regulatory} tone="rose" />
          <SummaryChip label={summary.relationships === 1 ? 'relationship' : 'relationships'} value={summary.relationships} tone="ink" />
        </div>
      )}

      <div className="mt-4 grid gap-6 lg:grid-cols-[1fr_320px]">
        {subgraph && (
          <ProductGraph
            nodes={subgraph.nodes}
            edges={subgraph.edges}
            primaryId={activeId}
            selectedId={selected?.id ?? null}
            onSelect={onSelectNode}
          />
        )}

        <div className="space-y-4">
          {selected && subgraph ? (
            <NodeDetail node={selected} nodes={subgraph.nodes} edges={subgraph.edges} />
          ) : (
            <div className="card p-5">
              <SectionHeading title="Inspect a node" />
              <p className="text-sm leading-relaxed text-ink-500">
                Click your product, the standard, or the regulatory order to see what it is and why
                these are connected. Each connection quotes the record it came from.
              </p>
              <div className="mt-4 space-y-2 text-xs text-ink-500">
                <LegendRow swatch="bg-violet-100 ring-violet-300" label="Your product" />
                <LegendRow swatch="bg-brand-100 ring-brand-400" label="Primary standard (covers the product)" />
                <LegendRow swatch="bg-rose-100 ring-rose-300" label="Regulatory order (makes it mandatory)" />
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="mt-6">
        <DisclaimerBanner
          compact
          text="Product view shows verified sources only. Every node is a stored standard or regulatory record and every solid edge is a stored relationship that cites the clause stating it; nothing here is generated by a language model."
        />
      </div>
    </>
  )
}

function SummaryChip({
  value,
  label,
  tone,
}: {
  value: number
  label: string
  tone: 'brand' | 'rose' | 'ink'
}) {
  const tones = {
    brand: 'bg-brand-50 text-brand-800 ring-brand-200',
    rose: 'bg-rose-50 text-rose-800 ring-rose-200',
    ink: 'bg-ink-100 text-ink-700 ring-ink-200',
  }
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 font-medium ring-1 ${tones[tone]}`}>
      <span className="text-sm font-bold">{value}</span>
      {label}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Advanced (full corpus) view
// ---------------------------------------------------------------------------

function AdvancedView() {
  const [data, setData] = useState<StandardsGraphResponse | null>(null)
  const [category, setCategory] = useState('')
  const [focus, setFocus] = useState('')
  const [showRegulatory, setShowRegulatory] = useState(true)
  const [selected, setSelected] = useState<GraphNode | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  const load = useCallback(() => {
    setLoading(true)
    setError('')
    api
      .standardsGraph({ category, focus, regulatory: showRegulatory })
      .then((d) => {
        setData(d)
        setSelected(null)
      })
      .catch((e) => setError(apiError(e)))
      .finally(() => setLoading(false))
  }, [category, focus, showRegulatory])

  useEffect(load, [load])

  const focusOnNode = (node: GraphNode) => {
    if (node.type === 'standard' && node.standard_id) {
      setFocus(node.standard_id)
      setCategory('')
    }
  }

  return (
    <>
      <div className="mt-6 flex flex-wrap items-end gap-3">
        <div>
          <label className="label" htmlFor="graph-category">
            Category
          </label>
          <select
            id="graph-category"
            className="field w-56"
            value={category}
            disabled={!!focus}
            onChange={(e) => setCategory(e.target.value)}
          >
            <option value="">All categories</option>
            {(data?.categories ?? []).map((c) => (
              <option key={c} value={c}>
                {titleCase(c)}
              </option>
            ))}
          </select>
        </div>

        <label className="flex items-center gap-2 rounded-xl border border-ink-200 bg-white px-3.5 py-2.5 text-sm font-medium text-ink-700">
          <input
            type="checkbox"
            className="h-4 w-4 rounded border-ink-300 text-brand-600 focus:ring-brand-500"
            checked={showRegulatory}
            onChange={(e) => setShowRegulatory(e.target.checked)}
          />
          Show regulatory (QCO) nodes
        </label>

        {focus && (
          <button className="btn-secondary btn-sm" onClick={() => setFocus('')}>
            <Crosshair className="h-3.5 w-3.5" />
            Clear focus
          </button>
        )}
      </div>

      {loading && (
        <div className="mt-6">
          <LoadingSkeleton rows={2} />
        </div>
      )}
      {error && (
        <div className="mt-6">
          <ErrorState message={error} onRetry={load} />
        </div>
      )}

      {!loading && !error && data && (
        <>
          {data.available ? (
            <>
              <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
                <Stat label="Standards" value={data.stats.standards} tone="brand" />
                <Stat label="Relationships" value={data.stats.edges} />
                <Stat label="Relationship types" value={data.stats.relationship_types} />
                <Stat label="Regulatory nodes" value={data.stats.regulatory_nodes} tone="warn" />
              </div>

              <div className="mt-6 grid gap-6 lg:grid-cols-[1fr_320px]">
                <CorpusGraph
                  nodes={data.nodes}
                  edges={data.edges}
                  relationshipTypes={data.relationship_types}
                  selectedId={selected?.id ?? null}
                  onSelect={setSelected}
                />

                <div className="space-y-4">
                  {selected ? (
                    <NodeDetail
                      node={selected}
                      nodes={data.nodes}
                      edges={data.edges}
                      onFocus={() => focusOnNode(selected)}
                    />
                  ) : (
                    <div className="card p-5">
                      <SectionHeading title="Inspect a node" />
                      <p className="text-sm leading-relaxed text-ink-500">
                        Click any standard or QCO in the graph to see what it connects to and why.
                        Each connection quotes the record it came from.
                      </p>
                      <div className="mt-4 space-y-2 text-xs text-ink-500">
                        <LegendRow swatch="bg-rose-100 ring-rose-300" label="Mandatory (QCO in force)" />
                        <LegendRow swatch="bg-amber-100 ring-amber-300" label="Upcoming regulation" />
                        <LegendRow swatch="bg-blue-100 ring-blue-300" label="Voluntary" />
                        <LegendRow swatch="bg-slate-100 ring-slate-300" label="Unable to verify / withdrawn" />
                      </div>
                    </div>
                  )}
                </div>
              </div>

              <div className="mt-6">
                <DisclaimerBanner text={data.note} compact />
              </div>
            </>
          ) : (
            <div className="mt-6">
              <EmptyState
                icon={<Workflow className="h-5 w-5" />}
                title="No relationships to draw"
                description={
                  focus
                    ? 'This standard has no stored relationships in the current corpus.'
                    : 'No standards match the current filter, so no graph is drawn.'
                }
                action={
                  (focus || category) && (
                    <button
                      className="btn-secondary btn-sm"
                      onClick={() => {
                        setFocus('')
                        setCategory('')
                      }}
                    >
                      Reset filters
                    </button>
                  )
                }
              />
            </div>
          )}
        </>
      )}
    </>
  )
}

// ---------------------------------------------------------------------------
// Shared node detail panel
// ---------------------------------------------------------------------------

function LegendRow({ swatch, label }: { swatch: string; label: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className={`h-3 w-5 rounded ring-1 ${swatch}`} />
      {label}
    </div>
  )
}

function NodeDetail({
  node,
  nodes,
  edges,
  onFocus,
}: {
  node: GraphNode
  nodes: GraphNode[]
  edges: GraphEdge[]
  onFocus?: () => void
}) {
  const outgoing = edges.filter((e) => e.source === node.id)
  const incoming = edges.filter((e) => e.target === node.id)
  const labelFor = (id: string) => nodes.find((n) => n.id === id)?.label ?? id

  if (node.type === 'product') {
    return (
      <div className="card p-5">
        <div className="flex flex-wrap items-center gap-2">
          <span className="chip bg-violet-50 text-violet-700 ring-1 ring-violet-200">
            <Package className="h-3 w-3" />
            Your product
          </span>
        </div>
        <h3 className="mt-2 text-sm font-bold leading-snug text-ink-900">{node.label}</h3>
        <p className="mt-1 text-xs leading-relaxed text-ink-500">
          The product you are exploring. It connects to the BIS product standard whose scope covers
          it.
        </p>
        {outgoing.length > 0 && (
          <div className="mt-4 space-y-2">
            {outgoing.map((e, i) => (
              <div key={i} className="rounded-lg border border-ink-100 bg-ink-50/50 p-2.5 text-xs">
                <span className="font-semibold text-ink-800">{e.label}</span>{' '}
                <span className="text-ink-500">→ {labelFor(e.target)}</span>
                {e.evidence && <p className="mt-1 leading-relaxed text-ink-500">{e.evidence}</p>}
              </div>
            ))}
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="card p-5">
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded bg-ink-900 px-2 py-0.5 font-mono text-[11px] font-bold text-white">
          {node.label}
        </span>
        {node.is_demo && <DemoDataBadge compact />}
        {node.type === 'standard' && node.regulatory && (
          <RegulatoryBadge status={node.regulatory as RegulatoryStatusValue} verified={!node.is_demo} />
        )}
      </div>

      {node.title && <h3 className="mt-2 text-sm font-bold leading-snug text-ink-900">{node.title}</h3>}

      {node.type === 'standard' ? (
        <>
          <p className="mt-1 text-xs text-ink-500">
            {node.category ? titleCase(node.category) : 'Uncategorised'}
            {typeof node.clause_count === 'number' && ` · ${node.clause_count} clauses`}
            {typeof node.requirement_count === 'number' && ` · ${node.requirement_count} requirements`}
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            {node.standard_id && (
              <Link to={`/standards/${node.standard_id}`} className="btn-secondary btn-sm">
                <ExternalLink className="h-3.5 w-3.5" />
                Open standard
              </Link>
            )}
            {onFocus && (
              <button className="btn-secondary btn-sm" onClick={onFocus}>
                <Crosshair className="h-3.5 w-3.5" />
                Focus neighbourhood
              </button>
            )}
          </div>
        </>
      ) : (
        node.ministry && <p className="mt-1 text-xs text-ink-500">{node.ministry}</p>
      )}

      {(outgoing.length > 0 || incoming.length > 0) && (
        <div className="mt-4 space-y-3">
          <p className="section-title">Why these are connected</p>
          {outgoing.length > 0 && (
            <div>
              <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-ink-400">
                <ShieldCheck className="mr-1 inline h-3 w-3" />
                This node →
              </p>
              <ul className="space-y-2">
                {outgoing.map((e, i) => (
                  <li key={i} className="rounded-lg border border-ink-100 bg-ink-50/50 p-2.5 text-xs">
                    <span className="font-semibold text-ink-800">{e.label}</span>{' '}
                    <span className="text-ink-500">→ {labelFor(e.target)}</span>
                    {e.evidence && <p className="mt-1 leading-relaxed text-ink-500">{e.evidence}</p>}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {incoming.length > 0 && (
            <div>
              <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-ink-400">
                → This node
              </p>
              <ul className="space-y-2">
                {incoming.map((e, i) => (
                  <li key={i} className="rounded-lg border border-ink-100 bg-ink-50/50 p-2.5 text-xs">
                    <span className="text-ink-500">{labelFor(e.source)} </span>
                    <span className="font-semibold text-ink-800">{e.label}</span>
                    {e.evidence && <p className="mt-1 leading-relaxed text-ink-500">{e.evidence}</p>}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {outgoing.length === 0 && incoming.length === 0 && (
        <p className="mt-3 text-xs text-ink-400">
          No stored relationships connect to this node in the current view.
        </p>
      )}
    </div>
  )
}
