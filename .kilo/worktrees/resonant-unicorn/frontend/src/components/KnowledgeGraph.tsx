import { useMemo } from 'react'
import type { GraphEdge, GraphNode } from '@/lib/types'

/**
 * Standards knowledge graph rendered as inline SVG.
 *
 * Every node and edge comes from a real record (a match, a normative reference
 * recorded in a document, or a regulatory record). If the backend reports no
 * relationships, nothing is drawn rather than a fabricated diagram.
 */
export function KnowledgeGraph({
  nodes,
  edges,
}: {
  nodes: GraphNode[]
  edges: GraphEdge[]
}) {
  const layout = useMemo(() => computeLayout(nodes), [nodes])

  if (nodes.length === 0) {
    return (
      <div className="card px-6 py-10 text-center text-sm text-ink-500">
        No relationship records are available for these standards, so no graph is drawn.
      </div>
    )
  }

  const width = 860
  const height = Math.max(300, layout.height)

  return (
    <div className="card overflow-hidden">
      <div className="scroll-thin overflow-x-auto p-4">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="h-auto w-full min-w-[720px]"
          role="img"
          aria-label="Standards knowledge graph"
        >
          <defs>
            <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" className="fill-ink-300" />
            </marker>
          </defs>

          {edges.map((edge, i) => {
            const from = layout.positions[edge.source]
            const to = layout.positions[edge.target]
            if (!from || !to) return null
            const midX = (from.x + to.x) / 2
            const midY = (from.y + to.y) / 2
            return (
              <g key={`${edge.source}-${edge.target}-${i}`}>
                <line
                  x1={from.x + 66}
                  y1={from.y}
                  x2={to.x - 66}
                  y2={to.y}
                  className="stroke-ink-200"
                  strokeWidth={1.5}
                  markerEnd="url(#arrow)"
                />
                <text
                  x={midX}
                  y={midY - 6}
                  textAnchor="middle"
                  className="fill-ink-400 text-[9px] font-semibold uppercase tracking-wide"
                >
                  {edge.label.slice(0, 26)}
                </text>
              </g>
            )
          })}

          {nodes.map((node) => {
            const pos = layout.positions[node.id]
            if (!pos) return null
            const style = NODE_STYLES[node.type] ?? NODE_STYLES.standard
            return (
              <g key={node.id} transform={`translate(${pos.x}, ${pos.y})`}>
                <title>{node.title || node.label}</title>
                <rect
                  x={-64}
                  y={-20}
                  width={128}
                  height={40}
                  rx={10}
                  className={`${style.fill} ${style.stroke}`}
                  strokeWidth={1.5}
                />
                <text textAnchor="middle" y={-2} className={`${style.text} text-[11px] font-bold`}>
                  {node.label.slice(0, 18)}
                </text>
                <text textAnchor="middle" y={11} className="fill-ink-400 text-[8.5px] font-semibold uppercase tracking-wider">
                  {node.relevance ?? node.type}
                </text>
              </g>
            )
          })}
        </svg>
      </div>

      <div className="flex flex-wrap gap-3 border-t border-ink-200 bg-ink-50/60 px-4 py-2.5 text-xs text-ink-500">
        {Object.entries(NODE_STYLES).map(([type, style]) => (
          <span key={type} className="inline-flex items-center gap-1.5">
            <span className={`h-2.5 w-2.5 rounded ${style.legend}`} />
            {type}
          </span>
        ))}
        <span className="ml-auto">Every edge is backed by a stored record.</span>
      </div>
    </div>
  )
}

const NODE_STYLES: Record<string, { fill: string; stroke: string; text: string; legend: string }> = {
  product: {
    fill: 'fill-violet-50',
    stroke: 'stroke-violet-300',
    text: 'fill-violet-900',
    legend: 'bg-violet-300',
  },
  standard: {
    fill: 'fill-brand-50',
    stroke: 'stroke-brand-300',
    text: 'fill-brand-900',
    legend: 'bg-brand-300',
  },
  qco: {
    fill: 'fill-rose-50',
    stroke: 'stroke-rose-300',
    text: 'fill-rose-900',
    legend: 'bg-rose-300',
  },
}

/** Simple layered layout: product -> standards -> regulatory records. */
function computeLayout(nodes: GraphNode[]) {
  const layers: Record<string, GraphNode[]> = { product: [], standard: [], qco: [] }
  nodes.forEach((n) => {
    ;(layers[n.type] ?? layers.standard).push(n)
  })

  const columns = [layers.product, layers.standard, layers.qco].filter((c) => c.length > 0)
  const positions: Record<string, { x: number; y: number }> = {}
  const rowGap = 72
  const maxRows = Math.max(...columns.map((c) => c.length), 1)
  const height = maxRows * rowGap + 60

  columns.forEach((column, columnIndex) => {
    const x = 100 + columnIndex * ((860 - 200) / Math.max(columns.length - 1, 1))
    column.forEach((node, rowIndex) => {
      const offset = (maxRows - column.length) / 2
      positions[node.id] = { x, y: 46 + (rowIndex + offset) * rowGap }
    })
  })

  return { positions, height }
}
