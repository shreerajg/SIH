import { useMemo } from 'react'
import type { GraphEdge, GraphNode } from '@/lib/types'

/**
 * Product-scoped standards graph, laid out as clean left-to-right layers:
 *
 *     your product  →  the standard(s) that cover it  →  the regulation
 *
 * It renders only what the backend supplied as stored records. The single
 * "product" node is the item the user chose to explore — it is drawn with a
 * dashed connector and never presented as a cited relationship, so nothing on
 * screen is mistaken for evidence the corpus does not hold.
 */

const WIDTH = 820

export type NodeRole = 'product' | 'primary' | 'related' | 'amendment' | 'qco'

/** Which visual role a node plays, from its stored type and the chosen primary. */
export function roleOf(node: GraphNode, primaryId: string): NodeRole {
  if (node.type === 'product') return 'product'
  if (node.type === 'qco') return 'qco'
  if (node.standard_id && node.standard_id === primaryId) return 'primary'
  if (/amendment/i.test(node.title || '')) return 'amendment'
  return 'related'
}

const STYLES: Record<NodeRole, { fill: string; stroke: string; strokeSel: string; text: string; sub: string; legend: string; caption: string }> = {
  product: {
    fill: 'fill-violet-50', stroke: 'stroke-violet-300', strokeSel: 'stroke-violet-500',
    text: 'fill-violet-900', sub: 'fill-violet-400', legend: 'bg-violet-100 ring-violet-300', caption: 'Your product',
  },
  primary: {
    fill: 'fill-brand-50', stroke: 'stroke-brand-400', strokeSel: 'stroke-brand-700',
    text: 'fill-brand-900', sub: 'fill-brand-500', legend: 'bg-brand-100 ring-brand-400', caption: 'Primary standard',
  },
  related: {
    fill: 'fill-slate-50', stroke: 'stroke-slate-300', strokeSel: 'stroke-slate-500',
    text: 'fill-ink-800', sub: 'fill-ink-400', legend: 'bg-slate-100 ring-slate-300', caption: 'Related standard',
  },
  amendment: {
    fill: 'fill-amber-50', stroke: 'stroke-amber-300', strokeSel: 'stroke-amber-500',
    text: 'fill-amber-900', sub: 'fill-amber-500', legend: 'bg-amber-100 ring-amber-300', caption: 'Amendment',
  },
  qco: {
    fill: 'fill-rose-50', stroke: 'stroke-rose-300', strokeSel: 'stroke-rose-600',
    text: 'fill-rose-900', sub: 'fill-rose-400', legend: 'bg-rose-100 ring-rose-300', caption: 'Regulatory order',
  },
}

/** Legend entries in the order they should appear, filtered to roles present. */
const LEGEND_ORDER: NodeRole[] = ['product', 'primary', 'related', 'amendment', 'qco']

const COLUMN_OF: Record<NodeRole, number> = { product: 0, primary: 1, related: 1, amendment: 2, qco: 2 }

const HALF_W = 68
const NODE_H = 46
const ROW_GAP = 74

function short(text: string, max = 20): string {
  const t = text || ''
  return t.length > max ? `${t.slice(0, max - 1)}…` : t
}

export function ProductGraph({
  nodes,
  edges,
  primaryId,
  selectedId,
  onSelect,
}: {
  nodes: GraphNode[]
  edges: GraphEdge[]
  primaryId: string
  selectedId: string | null
  onSelect: (node: GraphNode | null) => void
}) {
  const { positions, height } = useMemo(() => layout(nodes, primaryId), [nodes, primaryId])

  const neighbours = useMemo(() => {
    if (!selectedId) return null
    const set = new Set<string>([selectedId])
    edges.forEach((e) => {
      if (e.source === selectedId) set.add(e.target)
      if (e.target === selectedId) set.add(e.source)
    })
    return set
  }, [selectedId, edges])

  const rolesPresent = useMemo(() => {
    const seen = new Set<NodeRole>()
    nodes.forEach((n) => seen.add(roleOf(n, primaryId)))
    return LEGEND_ORDER.filter((r) => seen.has(r))
  }, [nodes, primaryId])

  if (nodes.length === 0) {
    return (
      <div className="card px-6 py-10 text-center text-sm text-ink-500">
        No stored records connect to this standard, so no graph is drawn.
      </div>
    )
  }

  const dimmed = (id: string) => (neighbours ? !neighbours.has(id) : false)

  return (
    <div className="card overflow-hidden">
      <div className="scroll-thin overflow-x-auto p-4">
        <svg
          viewBox={`0 0 ${WIDTH} ${height}`}
          className="h-auto w-full min-w-[640px]"
          role="img"
          aria-label="Product standards graph"
          onClick={() => onSelect(null)}
        >
          <defs>
            <marker id="pg-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" className="fill-ink-300" />
            </marker>
          </defs>

          {/* Edges */}
          {edges.map((edge, i) => {
            const from = positions[edge.source]
            const to = positions[edge.target]
            if (!from || !to) return null
            const dim = dimmed(edge.source) && dimmed(edge.target)
            const synthetic = edge.type === 'covered_by'
            const midX = (from.x + to.x) / 2
            const midY = (from.y + to.y) / 2
            const x1 = from.x + HALF_W
            const x2 = to.x - HALF_W
            return (
              <g key={`${edge.source}-${edge.target}-${i}`} opacity={dim ? 0.2 : 1}>
                <line
                  x1={x1}
                  y1={from.y}
                  x2={x2}
                  y2={to.y}
                  className="stroke-ink-300"
                  strokeWidth={1.6}
                  strokeDasharray={synthetic ? '5 4' : undefined}
                  markerEnd="url(#pg-arrow)"
                />
                <title>{edge.evidence || edge.label}</title>
                <text
                  x={midX}
                  y={midY - 7}
                  textAnchor="middle"
                  className="fill-ink-400 text-[9px] font-semibold uppercase tracking-wide"
                >
                  {short(edge.label, 22)}
                </text>
              </g>
            )
          })}

          {/* Nodes */}
          {nodes.map((node) => {
            const pos = positions[node.id]
            if (!pos) return null
            const role = roleOf(node, primaryId)
            const style = STYLES[role]
            const selected = node.id === selectedId
            const dim = dimmed(node.id)
            return (
              <g
                key={node.id}
                transform={`translate(${pos.x}, ${pos.y})`}
                opacity={dim ? 0.28 : 1}
                className="cursor-pointer"
                onClick={(e) => {
                  e.stopPropagation()
                  onSelect(selected ? null : node)
                }}
              >
                <title>{node.title || node.label}</title>
                <rect
                  x={-HALF_W}
                  y={-NODE_H / 2}
                  width={HALF_W * 2}
                  height={NODE_H}
                  rx={11}
                  className={`${style.fill} ${selected ? style.strokeSel : style.stroke}`}
                  strokeWidth={selected || role === 'primary' ? 2.5 : 1.5}
                />
                <text textAnchor="middle" y={-3} className={`${style.text} text-[11px] font-bold`}>
                  {short(node.label)}
                </text>
                <text textAnchor="middle" y={11} className={`${style.sub} text-[8px] font-semibold uppercase tracking-wider`}>
                  {style.caption}
                </text>
              </g>
            )
          })}
        </svg>
      </div>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-ink-200 bg-ink-50/60 px-4 py-2.5 text-xs text-ink-600">
        {rolesPresent.map((r) => (
          <span key={r} className="inline-flex items-center gap-1.5">
            <span className={`h-2.5 w-3.5 rounded ring-1 ${STYLES[r].legend}`} />
            {STYLES[r].caption}
          </span>
        ))}
        <span className="ml-auto text-ink-400">Click a node to see how it connects.</span>
      </div>
    </div>
  )
}

/** Layered layout: product | standards | regulatory, each column centred. */
function layout(nodes: GraphNode[], primaryId: string) {
  const columns: GraphNode[][] = [[], [], []]
  nodes.forEach((n) => {
    columns[COLUMN_OF[roleOf(n, primaryId)]].push(n)
  })
  // Keep the primary at the top of its column for a stable, readable order.
  columns[1].sort((a, b) => (a.standard_id === primaryId ? -1 : b.standard_id === primaryId ? 1 : 0))

  const present = columns.map((c, i) => ({ c, i })).filter((x) => x.c.length > 0)
  const maxRows = Math.max(...columns.map((c) => c.length), 1)
  const height = maxRows * ROW_GAP + 40
  const positions: Record<string, { x: number; y: number }> = {}
  const usableW = WIDTH - 220

  present.forEach(({ c, i: colIndex }, orderIndex) => {
    // Space present columns evenly across the canvas; keep original left→right order.
    void colIndex
    const x = present.length === 1 ? WIDTH / 2 : 110 + orderIndex * (usableW / (present.length - 1))
    const offset = (maxRows - c.length) / 2
    c.forEach((node, row) => {
      positions[node.id] = { x, y: 34 + (row + offset) * ROW_GAP + NODE_H / 2 }
    })
  })

  return { positions, height }
}
