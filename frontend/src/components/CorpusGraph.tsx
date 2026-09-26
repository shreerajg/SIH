import { useMemo } from 'react'
import type { GraphEdge, GraphNode, RelationshipType } from '@/lib/types'

/**
 * Corpus-wide standards knowledge graph, laid out with a small deterministic
 * force simulation and rendered as inline SVG.
 *
 * Deterministic on purpose: the same corpus always draws the same graph, which
 * matters for a demo and keeps it testable. Nothing is drawn that the backend
 * did not supply as a stored record.
 */

const WIDTH = 900
const HEIGHT = 560

/** Distinct, colour-blind-friendly hues per relationship type, assigned in order. */
const EDGE_COLORS = ['#2563eb', '#0d9488', '#d97706', '#7c3aed', '#db2777', '#4b5563', '#0891b2']

type Pos = { x: number; y: number }

export function CorpusGraph({
  nodes,
  edges,
  relationshipTypes,
  selectedId,
  onSelect,
}: {
  nodes: GraphNode[]
  edges: GraphEdge[]
  relationshipTypes: RelationshipType[]
  selectedId: string | null
  onSelect: (node: GraphNode | null) => void
}) {
  const colorForType = useMemo(() => {
    const map: Record<string, string> = {}
    relationshipTypes.forEach((r, i) => {
      map[r.type] = EDGE_COLORS[i % EDGE_COLORS.length]
    })
    return map
  }, [relationshipTypes])

  const positions = useMemo(() => layout(nodes, edges), [nodes, edges])

  const neighbours = useMemo(() => {
    if (!selectedId) return null
    const set = new Set<string>([selectedId])
    edges.forEach((e) => {
      if (e.source === selectedId) set.add(e.target)
      if (e.target === selectedId) set.add(e.source)
    })
    return set
  }, [selectedId, edges])

  if (nodes.length === 0) return null

  const isDimmed = (id: string) => (neighbours ? !neighbours.has(id) : false)

  return (
    <div className="card overflow-hidden">
      <div className="scroll-thin overflow-x-auto">
        <svg
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          className="h-auto w-full min-w-[680px]"
          role="img"
          aria-label="Standards knowledge graph"
          onClick={() => onSelect(null)}
        >
          <defs>
            {EDGE_COLORS.map((c, i) => (
              <marker
                key={i}
                id={`arrow-${i}`}
                viewBox="0 0 10 10"
                refX="9"
                refY="5"
                markerWidth="6"
                markerHeight="6"
                orient="auto-start-reverse"
              >
                <path d="M 0 0 L 10 5 L 0 10 z" fill={c} />
              </marker>
            ))}
          </defs>

          {/* Edges */}
          {edges.map((edge, i) => {
            const from = positions[edge.source]
            const to = positions[edge.target]
            if (!from || !to) return null
            const color = colorForType[edge.type] ?? '#94a3b8'
            const markerIdx = relationshipTypes.findIndex((r) => r.type === edge.type)
            const dim = isDimmed(edge.source) && isDimmed(edge.target)
            // Shorten the line so the arrowhead sits at the node edge, not under it.
            const dx = to.x - from.x
            const dy = to.y - from.y
            const len = Math.hypot(dx, dy) || 1
            const ux = dx / len
            const uy = dy / len
            const x1 = from.x + ux * 34
            const y1 = from.y + uy * 22
            const x2 = to.x - ux * 34
            const y2 = to.y - uy * 22
            return (
              <line
                key={`${edge.source}-${edge.target}-${i}`}
                x1={x1}
                y1={y1}
                x2={x2}
                y2={y2}
                stroke={color}
                strokeWidth={neighbours && !dim ? 2.2 : 1.4}
                strokeOpacity={dim ? 0.12 : 0.75}
                markerEnd={markerIdx >= 0 ? `url(#arrow-${markerIdx % EDGE_COLORS.length})` : undefined}
              >
                <title>{edge.evidence || edge.label}</title>
              </line>
            )
          })}

          {/* Nodes */}
          {nodes.map((node) => {
            const pos = positions[node.id]
            if (!pos) return null
            const dim = isDimmed(node.id)
            const selected = node.id === selectedId
            return (
              <g
                key={node.id}
                transform={`translate(${pos.x}, ${pos.y})`}
                opacity={dim ? 0.3 : 1}
                className="cursor-pointer"
                onClick={(e) => {
                  e.stopPropagation()
                  onSelect(selected ? null : node)
                }}
              >
                <title>{node.title || node.label}</title>
                {node.type === 'qco' ? (
                  <QcoNode node={node} selected={selected} />
                ) : (
                  <StandardNode node={node} selected={selected} />
                )}
              </g>
            )
          })}
        </svg>
      </div>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-ink-200 bg-ink-50/60 px-4 py-3 text-xs">
        {relationshipTypes.map((r) => (
          <span key={r.type} className="inline-flex items-center gap-1.5 text-ink-600" title={r.description}>
            <span
              className="h-0.5 w-5 rounded-full"
              style={{ backgroundColor: colorForType[r.type] }}
            />
            {r.label}
          </span>
        ))}
        <span className="ml-auto text-ink-400">Click a node to focus its connections.</span>
      </div>
    </div>
  )
}

function regulatoryFill(status?: string): { fill: string; stroke: string } {
  switch (status) {
    case 'MANDATORY':
      return { fill: '#fff1f2', stroke: '#fb7185' }
    case 'UPCOMING':
      return { fill: '#fffbeb', stroke: '#fbbf24' }
    case 'WITHDRAWN':
      return { fill: '#f1f5f9', stroke: '#cbd5e1' }
    case 'VOLUNTARY':
      return { fill: '#eff6ff', stroke: '#60a5fa' }
    default:
      return { fill: '#f8fafc', stroke: '#cbd5e1' }
  }
}

function StandardNode({ node, selected }: { node: GraphNode; selected: boolean }) {
  const c = regulatoryFill(node.regulatory)
  return (
    <>
      <rect
        x={-58}
        y={-19}
        width={116}
        height={38}
        rx={9}
        fill={c.fill}
        stroke={selected ? '#1e3a8a' : c.stroke}
        strokeWidth={selected ? 2.5 : 1.5}
      />
      <text textAnchor="middle" y={-2} className="fill-ink-900 text-[10.5px] font-bold">
        {node.label.length > 16 ? `${node.label.slice(0, 15)}…` : node.label}
      </text>
      <text
        textAnchor="middle"
        y={10}
        className="fill-ink-400 text-[8px] font-semibold uppercase tracking-wider"
      >
        {node.is_demo ? 'demo · ' : ''}
        {(node.regulatory ?? '').replace(/_/g, ' ').toLowerCase() || 'standard'}
      </text>
    </>
  )
}

function QcoNode({ node, selected }: { node: GraphNode; selected: boolean }) {
  return (
    <>
      <rect
        x={-44}
        y={-15}
        width={88}
        height={30}
        rx={15}
        fill="#fef2f2"
        stroke={selected ? '#991b1b' : '#f87171'}
        strokeWidth={selected ? 2.5 : 1.5}
      />
      <text textAnchor="middle" y={3.5} className="fill-rose-800 text-[9px] font-bold">
        {(node.label || 'QCO').length > 14 ? `${node.label.slice(0, 13)}…` : node.label || 'QCO'}
      </text>
    </>
  )
}

// ---------------------------------------------------------------------------
// Deterministic force-directed layout
// ---------------------------------------------------------------------------

function layout(nodes: GraphNode[], edges: GraphEdge[]): Record<string, Pos> {
  const n = nodes.length
  const cx = WIDTH / 2
  const cy = HEIGHT / 2
  const pos: Record<string, Pos> = {}
  const vel: Record<string, Pos> = {}

  // Seed on a circle, deterministically by index (no randomness).
  nodes.forEach((node, i) => {
    const angle = (i / Math.max(n, 1)) * Math.PI * 2
    const radius = Math.min(WIDTH, HEIGHT) * 0.32
    pos[node.id] = { x: cx + Math.cos(angle) * radius, y: cy + Math.sin(angle) * radius }
    vel[node.id] = { x: 0, y: 0 }
  })

  const adjacency = edges
    .map((e) => [e.source, e.target] as const)
    .filter(([a, b]) => pos[a] && pos[b])

  const REPULSION = 42000
  const SPRING = 0.02
  const REST = 150
  const GRAVITY = 0.015
  const DAMPING = 0.85
  const STEPS = 320

  for (let step = 0; step < STEPS; step++) {
    // Repulsion between every pair.
    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        const a = nodes[i].id
        const b = nodes[j].id
        let dx = pos[a].x - pos[b].x
        let dy = pos[a].y - pos[b].y
        let dist2 = dx * dx + dy * dy
        if (dist2 < 0.01) {
          dx = (i - j) * 0.1 + 0.1
          dy = 0.1
          dist2 = dx * dx + dy * dy
        }
        const dist = Math.sqrt(dist2)
        const force = REPULSION / dist2
        const fx = (dx / dist) * force
        const fy = (dy / dist) * force
        vel[a].x += fx
        vel[a].y += fy
        vel[b].x -= fx
        vel[b].y -= fy
      }
    }

    // Springs along edges.
    adjacency.forEach(([a, b]) => {
      const dx = pos[b].x - pos[a].x
      const dy = pos[b].y - pos[a].y
      const dist = Math.hypot(dx, dy) || 1
      const force = SPRING * (dist - REST)
      const fx = (dx / dist) * force
      const fy = (dy / dist) * force
      vel[a].x += fx
      vel[a].y += fy
      vel[b].x -= fx
      vel[b].y -= fy
    })

    // Gravity toward centre + integrate.
    nodes.forEach((node) => {
      const p = pos[node.id]
      const v = vel[node.id]
      v.x += (cx - p.x) * GRAVITY
      v.y += (cy - p.y) * GRAVITY
      v.x *= DAMPING
      v.y *= DAMPING
      p.x += v.x
      p.y += v.y
      // Keep inside the viewBox with a margin.
      p.x = Math.max(70, Math.min(WIDTH - 70, p.x))
      p.y = Math.max(34, Math.min(HEIGHT - 34, p.y))
    })
  }

  return pos
}
