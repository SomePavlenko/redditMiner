import { useEffect, useRef, useState, useCallback, useMemo } from 'react'
import { Link } from 'react-router-dom'

// ─── Types ────────────────────────────────────────────────────────────────────

export interface Idea {
  id: number
  title: string
  score: number
  subreddits: string
  solves_clusters: string
  description?: string
  demand_score?: number
}

interface ClusterInfo {
  id: number
  cluster_name: string
  pain_score?: number
  subreddits_json?: string
}

interface Props {
  ideas: Idea[]
  onSelect: (id: number) => void
}

// ─── Constants ────────────────────────────────────────────────────────────────

const IDEA_COLOR    = '#818cf8'
const CLUSTER_COLOR = '#f472b6'
const SUB_COLOR     = '#34d399'
const BG_COLOR      = '#0a0a0f'
const LINK_COLOR    = 'rgba(255,255,255,0.07)'
const LINK_HOVERED  = 'rgba(255,255,255,0.28)'
const DPR           = typeof window !== 'undefined' ? Math.min(window.devicePixelRatio || 1, 2) : 2
const CANVAS_HEIGHT = 520

// ─── Simulation types ─────────────────────────────────────────────────────────

interface SimNode {
  id: string
  label: string
  type: 'idea' | 'cluster' | 'subreddit'
  size: number          // logical radius (pre-scale)
  color: string
  // world-space coordinates
  x: number
  y: number
  vx: number
  vy: number
  // metadata for tooltip & detail card
  sourceId?: number     // DB id for ideas
  clusterId?: number    // DB id for clusters
  subName?: string      // subreddit name (without r/)
  score?: number
  clusterName?: string
  painScore?: number
}

interface SimLink {
  from: string
  to: string
}

interface Camera {
  x: number   // pan offset in canvas px
  y: number
  scale: number
}

interface TooltipState {
  visible: boolean
  x: number   // screen px
  y: number
  node: SimNode | null
}

// ─── Build graph from ideas ───────────────────────────────────────────────────

function buildGraph(ideas: Idea[], clusterMap: Map<number, ClusterInfo>) {
  const nodes: SimNode[] = []
  const links: SimLink[] = []
  const seen = new Set<string>()
  const linkSeen = new Set<string>()

  // Helper: add subreddit node if not exists
  function ensureSub(sub: string) {
    const key = `sub-${sub}`
    if (!seen.has(key)) {
      seen.add(key)
      nodes.push({
        id: key, label: `r/${sub}`, type: 'subreddit',
        size: 5, color: SUB_COLOR,
        x: 0, y: 0, vx: 0, vy: 0,
        subName: sub,
      })
    }
    return key
  }

  // Helper: add link if not duplicate
  function addLink(from: string, to: string) {
    const k = `${from}|${to}`
    if (!linkSeen.has(k)) { linkSeen.add(k); links.push({ from, to }) }
  }

  ideas.forEach(idea => {
    const ideaKey = `idea-${idea.id}`
    nodes.push({
      id: ideaKey,
      label: idea.title,
      type: 'idea',
      size: 6 + idea.score * 2.5,
      color: IDEA_COLOR,
      x: 0, y: 0, vx: 0, vy: 0,
      sourceId: idea.id,
      score: idea.score,
    })

    // Idea → Cluster links
    let clusterIds: number[] = []
    try { clusterIds = JSON.parse(idea.solves_clusters) || [] } catch { /* ignore */ }
    clusterIds.forEach(cid => {
      const key = `cl-${cid}`
      const info = clusterMap.get(cid)
      if (!seen.has(key)) {
        seen.add(key)
        nodes.push({
          id: key,
          label: info ? info.cluster_name : `#${cid}`,
          type: 'cluster',
          size: 4,
          color: CLUSTER_COLOR,
          x: 0, y: 0, vx: 0, vy: 0,
          clusterId: cid,
          clusterName: info?.cluster_name,
          painScore: info?.pain_score,
        })

        // Cluster → Subreddit links (from cluster's own data)
        if (info?.subreddits_json) {
          try {
            const subs: string[] = JSON.parse(info.subreddits_json) || []
            subs.forEach(sub => {
              const subKey = ensureSub(sub)
              addLink(key, subKey)
            })
          } catch { /* ignore */ }
        }
      }
      addLink(ideaKey, key)
    })
  })

  return { nodes, links }
}

// ─── Force simulation ─────────────────────────────────────────────────────────

function runTick(
  nodes: SimNode[],
  links: SimLink[],
  nodeMap: Map<string, SimNode>,
  W: number,
  H: number,
  dampingFactor: number,
) {
  const REPULSION    = 900
  const SPRING_LEN   = 130
  const SPRING_K     = 0.006
  const GRAVITY      = 0.0006
  const DAMPING      = dampingFactor

  // Repulsion (O(n^2) is fine for <300 nodes)
  for (let i = 0; i < nodes.length; i++) {
    for (let j = i + 1; j < nodes.length; j++) {
      const a = nodes[i], b = nodes[j]
      let dx = b.x - a.x
      let dy = b.y - a.y
      const dist2 = dx * dx + dy * dy || 1
      const dist  = Math.sqrt(dist2)
      const force = REPULSION / dist2
      const fx = (dx / dist) * force
      const fy = (dy / dist) * force
      a.vx -= fx; a.vy -= fy
      b.vx += fx; b.vy += fy
    }
  }

  // Spring attraction along links
  links.forEach(l => {
    const a = nodeMap.get(l.from)
    const b = nodeMap.get(l.to)
    if (!a || !b) return
    const dx   = b.x - a.x
    const dy   = b.y - a.y
    const dist = Math.sqrt(dx * dx + dy * dy) || 1
    const force = (dist - SPRING_LEN) * SPRING_K
    const fx = (dx / dist) * force
    const fy = (dy / dist) * force
    a.vx += fx; a.vy += fy
    b.vx -= fx; b.vy -= fy
  })

  // Center gravity
  nodes.forEach(n => {
    n.vx += (W / 2 - n.x) * GRAVITY
    n.vy += (H / 2 - n.y) * GRAVITY
  })

  // Integrate + dampen
  let totalMovement = 0
  nodes.forEach(n => {
    if ((n as any)._pinned) return
    n.vx *= DAMPING
    n.vy *= DAMPING
    n.x  += n.vx
    n.y  += n.vy
    totalMovement += Math.abs(n.vx) + Math.abs(n.vy)
    // soft boundary
    const margin = n.size + 10
    if (n.x < margin)     { n.x = margin;     n.vx *= -0.3 }
    if (n.x > W - margin) { n.x = W - margin; n.vx *= -0.3 }
    if (n.y < margin)     { n.y = margin;     n.vy *= -0.3 }
    if (n.y > H - margin) { n.y = H - margin; n.vy *= -0.3 }
  })

  return totalMovement
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function BubbleChart({ ideas }: Props) {
  const canvasRef      = useRef<HTMLCanvasElement>(null)
  const stateRef       = useRef<{
    nodes: SimNode[]
    links: SimLink[]
    nodeMap: Map<string, SimNode>
    camera: Camera
    hoveredId: string | null
    draggingNode: SimNode | null
    draggingCanvas: boolean
    dragStartX: number
    dragStartY: number
    dragStartCamX: number
    dragStartCamY: number
    simRunning: boolean
    rafId: number
    W: number
    H: number
    clusterMap: Map<number, ClusterInfo>
  }>({
    nodes: [], links: [], nodeMap: new Map(),
    camera: { x: 0, y: 0, scale: 1 },
    hoveredId: null,
    draggingNode: null,
    draggingCanvas: false,
    dragStartX: 0, dragStartY: 0,
    dragStartCamX: 0, dragStartCamY: 0,
    simRunning: false,
    rafId: 0,
    W: 0, H: 0,
    clusterMap: new Map(),
  })

  const [tooltip, setTooltip] = useState<TooltipState>({ visible: false, x: 0, y: 0, node: null })
  const tooltipRef = useRef<TooltipState>({ visible: false, x: 0, y: 0, node: null })
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)

  // ── helpers: coordinate transforms ──────────────────────────────────────────

  /** canvas px → world coords */
  const canvasToWorld = useCallback((cx: number, cy: number) => {
    const cam = stateRef.current.camera
    return {
      x: (cx - cam.x) / cam.scale,
      y: (cy - cam.y) / cam.scale,
    }
  }, [])

  // ── draw ─────────────────────────────────────────────────────────────────────

  const draw = useCallback(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const { nodes, links, nodeMap, camera, hoveredId, W, H } = stateRef.current

    ctx.clearRect(0, 0, W, H)

    // Dark background
    ctx.fillStyle = BG_COLOR
    ctx.fillRect(0, 0, W, H)

    ctx.save()
    ctx.translate(camera.x, camera.y)
    ctx.scale(camera.scale, camera.scale)

    // ── links ──
    links.forEach(l => {
      const a = nodeMap.get(l.from)
      const b = nodeMap.get(l.to)
      if (!a || !b) return
      const isHov = hoveredId === a.id || hoveredId === b.id
      ctx.beginPath()
      ctx.moveTo(a.x, a.y)
      ctx.lineTo(b.x, b.y)
      ctx.strokeStyle = isHov ? LINK_HOVERED : LINK_COLOR
      ctx.lineWidth   = isHov ? 1.5 / camera.scale : 0.8 / camera.scale
      ctx.stroke()
    })

    // ── nodes ──
    nodes.forEach(n => {
      const isHov = hoveredId === n.id
      const r     = n.size * (isHov ? 1.25 : 1)

      // Outer glow
      const glowRadius = r + (isHov ? 18 : 8)
      const grad = ctx.createRadialGradient(n.x, n.y, r * 0.5, n.x, n.y, glowRadius)
      grad.addColorStop(0, n.color + (isHov ? '55' : '22'))
      grad.addColorStop(1, n.color + '00')
      ctx.beginPath()
      ctx.arc(n.x, n.y, glowRadius, 0, Math.PI * 2)
      ctx.fillStyle = grad
      ctx.fill()

      // Node body
      ctx.beginPath()
      ctx.arc(n.x, n.y, r, 0, Math.PI * 2)
      ctx.fillStyle = isHov ? n.color : n.color + 'cc'
      ctx.fill()

      // Thin ring when hovered
      if (isHov) {
        ctx.beginPath()
        ctx.arc(n.x, n.y, r + 2 / camera.scale, 0, Math.PI * 2)
        ctx.strokeStyle = n.color + 'aa'
        ctx.lineWidth   = 1.5 / camera.scale
        ctx.stroke()
      }

      // Label
      const fontSize = Math.max(10, (n.type === 'idea' ? n.size * 1.2 : 10)) / camera.scale
      ctx.font        = `${n.type === 'idea' ? '500 ' : ''}${fontSize}px system-ui, sans-serif`
      ctx.fillStyle   = isHov ? '#ffffff' : 'rgba(255,255,255,0.65)'
      ctx.textAlign   = 'center'
      ctx.textBaseline = 'top'
      const maxLen = 22
      const label = n.label.length > maxLen ? n.label.slice(0, maxLen - 1) + '…' : n.label
      ctx.fillText(label, n.x, n.y + r + 3 / camera.scale)
    })

    ctx.restore()
  }, [])

  // ── simulation loop ──────────────────────────────────────────────────────────

  const startSimulation = useCallback(() => {
    const s = stateRef.current
    if (s.simRunning) return
    s.simRunning = true

    let stationaryFrames = 0
    const THRESHOLD      = 0.3 * s.nodes.length
    let damping          = 0.82  // start more energetic, cool down

    function simFrame() {
      const movement = runTick(s.nodes, s.links, s.nodeMap, s.W, s.H, damping)
      draw()

      // Gradually cool simulation
      damping = Math.min(0.96, damping + 0.002)

      if (movement < THRESHOLD) {
        stationaryFrames++
      } else {
        stationaryFrames = 0
      }

      if (stationaryFrames < 30) {
        s.rafId = requestAnimationFrame(simFrame)
      } else {
        s.simRunning = false
        draw() // final clean frame
      }
    }

    s.rafId = requestAnimationFrame(simFrame)
  }, [draw])

  // ── hit-test ─────────────────────────────────────────────────────────────────

  const hitTest = useCallback((canvasX: number, canvasY: number): SimNode | null => {
    const { nodes } = stateRef.current
    const world = canvasToWorld(canvasX, canvasY)
    for (const n of nodes) {
      const dx = world.x - n.x
      const dy = world.y - n.y
      const r  = n.size * 1.5
      if (dx * dx + dy * dy <= r * r) return n
    }
    return null
  }, [canvasToWorld])

  // ── mouse event handlers ─────────────────────────────────────────────────────

  const handleMouseMove = useCallback((e: MouseEvent) => {
    const canvas = canvasRef.current
    if (!canvas) return
    const rect = canvas.getBoundingClientRect()
    const cx   = (e.clientX - rect.left) * DPR
    const cy   = (e.clientY - rect.top)  * DPR
    const s    = stateRef.current

    // ── node drag ──
    if (s.draggingNode) {
      const world = canvasToWorld(cx, cy)
      s.draggingNode.x  = world.x
      s.draggingNode.y  = world.y
      s.draggingNode.vx = 0
      s.draggingNode.vy = 0
      draw()
      return
    }

    // ── canvas pan ──
    if (s.draggingCanvas) {
      s.camera.x = s.dragStartCamX + (e.clientX - s.dragStartX) * DPR
      s.camera.y = s.dragStartCamY + (e.clientY - s.dragStartY) * DPR
      draw()
      return
    }

    // ── hover ──
    const hit = hitTest(cx, cy)
    const newId = hit ? hit.id : null

    if (newId !== s.hoveredId) {
      s.hoveredId = newId
      canvas.style.cursor = hit ? 'pointer' : 'default'
      draw()
    }

    // Tooltip
    if (hit) {
      const tt: TooltipState = { visible: true, x: e.clientX, y: e.clientY, node: hit }
      tooltipRef.current = tt
      setTooltip(tt)
    } else if (tooltipRef.current.visible) {
      const tt: TooltipState = { visible: false, x: 0, y: 0, node: null }
      tooltipRef.current = tt
      setTooltip(tt)
    }
  }, [canvasToWorld, hitTest, draw])

  const handleMouseDown = useCallback((e: MouseEvent) => {
    const canvas = canvasRef.current
    if (!canvas) return
    const rect = canvas.getBoundingClientRect()
    const cx   = (e.clientX - rect.left) * DPR
    const cy   = (e.clientY - rect.top)  * DPR
    const s    = stateRef.current
    const hit  = hitTest(cx, cy)

    if (hit) {
      s.draggingNode = hit
      ;(hit as any)._pinned = true
    } else {
      s.draggingCanvas  = true
      s.dragStartX      = e.clientX
      s.dragStartY      = e.clientY
      s.dragStartCamX   = s.camera.x
      s.dragStartCamY   = s.camera.y
    }
    e.preventDefault()
  }, [hitTest])

  const handleMouseUp = useCallback((e: MouseEvent) => {
    const s = stateRef.current

    if (s.draggingNode) {
      ;(s.draggingNode as any)._pinned = false
      s.draggingNode = null
      // Kick simulation to re-settle after drop
      startSimulation()
    }
    s.draggingCanvas = false

    // Suppress tooltip flicker on mouse-up
    const canvas = canvasRef.current
    if (!canvas) return
    const rect = canvas.getBoundingClientRect()
    const cx   = (e.clientX - rect.left) * DPR
    const cy   = (e.clientY - rect.top)  * DPR
    const hit  = hitTest(cx, cy)
    if (!hit && tooltipRef.current.visible) {
      const tt: TooltipState = { visible: false, x: 0, y: 0, node: null }
      tooltipRef.current = tt
      setTooltip(tt)
    }
  }, [hitTest, startSimulation])

  const handleClick = useCallback((e: MouseEvent) => {
    const canvas = canvasRef.current
    if (!canvas) return
    const rect = canvas.getBoundingClientRect()
    const cx   = (e.clientX - rect.left) * DPR
    const cy   = (e.clientY - rect.top)  * DPR
    const hit  = hitTest(cx, cy)
    if (hit) {
      setSelectedNodeId(prev => prev === hit.id ? null : hit.id)
    } else {
      setSelectedNodeId(null)
    }
  }, [hitTest])

  const handleWheel = useCallback((e: WheelEvent) => {
    e.preventDefault()
    const canvas = canvasRef.current
    if (!canvas) return
    const rect   = canvas.getBoundingClientRect()
    const cx     = (e.clientX - rect.left) * DPR
    const cy     = (e.clientY - rect.top)  * DPR
    const s      = stateRef.current
    const factor = e.deltaY < 0 ? 1.1 : 0.909
    const newScale = Math.max(0.2, Math.min(5, s.camera.scale * factor))

    // Zoom towards cursor
    s.camera.x = cx - (cx - s.camera.x) * (newScale / s.camera.scale)
    s.camera.y = cy - (cy - s.camera.y) * (newScale / s.camera.scale)
    s.camera.scale = newScale
    draw()
  }, [draw])

  const handleMouseLeave = useCallback(() => {
    const s = stateRef.current
    s.hoveredId = null
    s.draggingCanvas = false
    if (s.draggingNode) {
      ;(s.draggingNode as any)._pinned = false
      s.draggingNode = null
      startSimulation()
    }
    const tt: TooltipState = { visible: false, x: 0, y: 0, node: null }
    tooltipRef.current = tt
    setTooltip(tt)
    draw()
  }, [draw, startSimulation])

  // ── fetch clusters, then build graph & start sim ──────────────────────────────

  useEffect(() => {
    let cancelled = false

    fetch('/api/clusters')
      .then(r => r.json())
      .then((data: ClusterInfo[]) => {
        if (cancelled) return
        const clusterMap = new Map<number, ClusterInfo>()
        data.forEach(c => clusterMap.set(c.id, c))
        stateRef.current.clusterMap = clusterMap
        initGraph(clusterMap)
      })
      .catch(() => {
        if (!cancelled) initGraph(new Map())
      })

    function initGraph(clusterMap: Map<number, ClusterInfo>) {
      const canvas = canvasRef.current
      if (!canvas || ideas.length === 0) return
      const ctx = canvas.getContext('2d')
      if (!ctx) return

      const W = canvas.offsetWidth * DPR
      const H = CANVAS_HEIGHT * DPR
      canvas.width  = W
      canvas.height = H
      canvas.style.height = `${CANVAS_HEIGHT}px`

      const s   = stateRef.current
      s.W       = W
      s.H       = H
      s.camera  = { x: 0, y: 0, scale: 1 }

      const { nodes, links } = buildGraph(ideas, clusterMap)

      // Scatter initial positions
      nodes.forEach(n => {
        n.x  = W / 2 + (Math.random() - 0.5) * W * 0.55
        n.y  = H / 2 + (Math.random() - 0.5) * H * 0.55
        n.vx = (Math.random() - 0.5) * 2
        n.vy = (Math.random() - 0.5) * 2
      })

      s.nodes   = nodes
      s.links   = links
      s.nodeMap = new Map(nodes.map(n => [n.id, n]))
      s.hoveredId = null

      if (s.rafId) cancelAnimationFrame(s.rafId)
      s.simRunning = false
      startSimulation()
    }

    return () => { cancelled = true }
  }, [ideas, startSimulation])

  // ── attach event listeners ────────────────────────────────────────────────────

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    canvas.addEventListener('mousemove',  handleMouseMove)
    canvas.addEventListener('mousedown',  handleMouseDown)
    canvas.addEventListener('mouseup',    handleMouseUp)
    canvas.addEventListener('click',      handleClick)
    canvas.addEventListener('wheel',      handleWheel, { passive: false })
    canvas.addEventListener('mouseleave', handleMouseLeave)

    return () => {
      canvas.removeEventListener('mousemove',  handleMouseMove)
      canvas.removeEventListener('mousedown',  handleMouseDown)
      canvas.removeEventListener('mouseup',    handleMouseUp)
      canvas.removeEventListener('click',      handleClick)
      canvas.removeEventListener('wheel',      handleWheel)
      canvas.removeEventListener('mouseleave', handleMouseLeave)
    }
  }, [handleMouseMove, handleMouseDown, handleMouseUp, handleClick, handleWheel, handleMouseLeave])

  // ── cleanup on unmount ────────────────────────────────────────────────────────

  useEffect(() => {
    return () => {
      if (stateRef.current.rafId) {
        cancelAnimationFrame(stateRef.current.rafId)
      }
    }
  }, [])

  // ─── Tooltip content ──────────────────────────────────────────────────────────

  function TooltipContent({ node }: { node: SimNode }) {
    if (node.type === 'idea') {
      return (
        <>
          <div className="font-semibold text-indigo-300 text-sm leading-snug mb-1">{node.label}</div>
          <div className="text-xs text-gray-400">
            Score: <span className="text-white font-medium">{node.score}</span>
          </div>
        </>
      )
    }
    if (node.type === 'cluster') {
      return (
        <>
          <div className="font-semibold text-pink-300 text-sm leading-snug mb-1">
            {node.clusterName ?? node.label}
          </div>
          {node.painScore != null && (
            <div className="text-xs text-gray-400">
              Pain score: <span className="text-white font-medium">{node.painScore}</span>
            </div>
          )}
        </>
      )
    }
    // subreddit
    return (
      <div className="font-semibold text-emerald-300 text-sm">{node.label}</div>
    )
  }

  // ─── Selected node detail card (snapshot data on selection, immune to hover re-renders) ───

  interface CardConn { id: string; label: string; type: 'idea' | 'cluster' | 'subreddit'; sourceId?: number; clusterId?: number; subName?: string; score?: number; clusterName?: string; painScore?: number }
  interface CardData { node: SimNode; ideas: CardConn[]; clusters: CardConn[]; subs: CardConn[] }

  const cardData = useMemo<CardData | null>(() => {
    if (!selectedNodeId) return null
    const s = stateRef.current
    const node = s.nodeMap.get(selectedNodeId)
    if (!node) return null
    const conns: CardConn[] = []
    s.links.forEach(l => {
      if (l.from === selectedNodeId) { const n = s.nodeMap.get(l.to); if (n) conns.push(n) }
      if (l.to === selectedNodeId) { const n = s.nodeMap.get(l.from); if (n) conns.push(n) }
    })
    return {
      node,
      ideas: conns.filter(n => n.type === 'idea'),
      clusters: conns.filter(n => n.type === 'cluster'),
      subs: conns.filter(n => n.type === 'subreddit'),
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedNodeId])

  // ─── Render ───────────────────────────────────────────────────────────────────

  return (
    <div className="relative select-none">
      <canvas
        ref={canvasRef}
        className="w-full rounded-xl border border-gray-800"
        style={{ background: BG_COLOR, display: 'block' }}
      />

      {/* Floating tooltip */}
      {tooltip.visible && tooltip.node && (
        <div
          className="fixed z-50 pointer-events-none px-3 py-2 rounded-lg border border-gray-700 bg-gray-900/95 shadow-xl backdrop-blur-sm max-w-xs"
          style={{
            left: tooltip.x + 14,
            top:  tooltip.y - 10,
            transform: 'translateY(-50%)',
          }}
        >
          <TooltipContent node={tooltip.node} />
        </div>
      )}

      {/* Selected node detail card */}
      {cardData && (() => {
        const { node, ideas: ic, clusters: cc, subs: sc } = cardData
        const typeLabel = node.type === 'idea' ? 'Идея' : node.type === 'cluster' ? 'Кластер боли' : 'Сабреддит'
        const typeColor = node.type === 'idea' ? 'text-indigo-400' : node.type === 'cluster' ? 'text-pink-400' : 'text-emerald-400'
        const hasConns = ic.length + cc.length + sc.length > 0
        return (
          <div className="mt-3 rounded-xl border border-gray-800 bg-gray-900/80 p-4">
            <div className="flex items-center gap-3 mb-3">
              <span className="w-3 h-3 rounded-full flex-shrink-0" style={{ background: node.color, boxShadow: `0 0 8px ${node.color}` }} />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className={`text-xs font-medium ${typeColor}`}>{typeLabel}</span>
                  {node.score != null && <span className="text-xs text-gray-500">Score: {node.score}</span>}
                  {node.painScore != null && <span className="text-xs text-gray-500">Pain: {node.painScore}</span>}
                </div>
                {node.type === 'idea' && node.sourceId != null ? (
                  <Link to={`/ideas/${node.sourceId}`} className="text-sm font-semibold text-white hover:underline">{node.label}</Link>
                ) : node.type === 'cluster' && node.clusterId != null ? (
                  <Link to={`/clusters/${node.clusterId}`} className="text-sm font-semibold text-white hover:underline">{node.label}</Link>
                ) : node.type === 'subreddit' && node.subName ? (
                  <a href={`https://reddit.com/r/${node.subName}`} target="_blank" rel="noopener noreferrer" className="text-sm font-semibold text-white hover:underline">{node.label}</a>
                ) : (
                  <span className="text-sm font-semibold text-white">{node.label}</span>
                )}
              </div>
              <button onClick={() => setSelectedNodeId(null)} className="text-gray-500 hover:text-gray-300 text-lg leading-none">&times;</button>
            </div>
            {hasConns ? (
              <div className="flex flex-wrap gap-6 text-xs">
                {ic.length > 0 && (
                  <div>
                    <div className="text-gray-500 mb-1.5 flex items-center gap-1.5">
                      <span className="w-2 h-2 rounded-full" style={{ background: IDEA_COLOR }} />
                      Идеи ({ic.length})
                    </div>
                    <ul className="space-y-1">
                      {ic.map(n => (
                        <li key={n.id}>
                          <Link to={`/ideas/${n.sourceId}`} className="text-indigo-300 hover:text-indigo-200 hover:underline">
                            {n.label}{n.score != null && <span className="text-gray-500 ml-1">({n.score})</span>}
                          </Link>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {cc.length > 0 && (
                  <div>
                    <div className="text-gray-500 mb-1.5 flex items-center gap-1.5">
                      <span className="w-2 h-2 rounded-full" style={{ background: CLUSTER_COLOR }} />
                      Кластеры ({cc.length})
                    </div>
                    <ul className="space-y-1">
                      {cc.map(n => (
                        <li key={n.id}>
                          <Link to={`/clusters/${n.clusterId}`} className="text-pink-300 hover:text-pink-200 hover:underline">
                            {n.clusterName ?? n.label}{n.painScore != null && <span className="text-gray-500 ml-1">({n.painScore})</span>}
                          </Link>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {sc.length > 0 && (
                  <div>
                    <div className="text-gray-500 mb-1.5 flex items-center gap-1.5">
                      <span className="w-2 h-2 rounded-full" style={{ background: SUB_COLOR }} />
                      Сабреддиты ({sc.length})
                    </div>
                    <ul className="space-y-1">
                      {sc.map(n => (
                        <li key={n.id}>
                          <a href={`https://reddit.com/r/${n.subName}`} target="_blank" rel="noopener noreferrer"
                             className="text-emerald-300 hover:text-emerald-200 hover:underline">{n.label}</a>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            ) : (
              <span className="text-xs text-gray-600">Нет связей</span>
            )}
          </div>
        )
      })()}

      {/* Legend */}
      <div className="flex gap-5 mt-2 text-xs text-gray-500 justify-center">
        <span className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full" style={{ background: IDEA_COLOR, boxShadow: `0 0 6px ${IDEA_COLOR}` }} />
          Идеи
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full" style={{ background: CLUSTER_COLOR, boxShadow: `0 0 6px ${CLUSTER_COLOR}` }} />
          Кластеры болей
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full" style={{ background: SUB_COLOR, boxShadow: `0 0 6px ${SUB_COLOR}` }} />
          Сабреддиты
        </span>
        <span className="text-gray-600">· Scroll to zoom · Drag to pan · Drag node to move</span>
      </div>
    </div>
  )
}
