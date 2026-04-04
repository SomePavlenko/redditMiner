import { useEffect, useRef, useMemo, useState } from 'react'

interface Idea {
  id: number
  title: string
  score: number
  subreddits: string
  solves_clusters: string
}

interface Props {
  ideas: Idea[]
  onSelect: (id: number) => void
}

const IDEA_COLOR = '#818cf8'
const CLUSTER_COLOR = '#f472b6'
const SUB_COLOR = '#34d399'
const LINK_COLOR = 'rgba(255,255,255,0.08)'

interface Node {
  id: string
  label: string
  type: 'idea' | 'cluster' | 'subreddit'
  size: number
  color: string
  x: number
  y: number
  vx: number
  vy: number
  sourceId?: number
}

interface Link {
  from: string
  to: string
}

export default function BubbleChart({ ideas, onSelect }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [hovered, setHovered] = useState<string | null>(null)
  const animRef = useRef<number>(0)

  const { nodes, links } = useMemo(() => {
    const nodes: Node[] = []
    const links: Link[] = []
    const seen = new Set<string>()

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
      })

      // Subreddits
      let subs: string[] = []
      try { subs = JSON.parse(idea.subreddits) || [] } catch {}
      subs.forEach(sub => {
        const subKey = `sub-${sub}`
        if (!seen.has(subKey)) {
          seen.add(subKey)
          nodes.push({
            id: subKey, label: `r/${sub}`, type: 'subreddit',
            size: 5, color: SUB_COLOR,
            x: 0, y: 0, vx: 0, vy: 0,
          })
        }
        links.push({ from: ideaKey, to: subKey })
      })

      // Clusters
      let clusters: number[] = []
      try { clusters = JSON.parse(idea.solves_clusters) || [] } catch {}
      clusters.forEach(cid => {
        const clKey = `cl-${cid}`
        if (!seen.has(clKey)) {
          seen.add(clKey)
          nodes.push({
            id: clKey, label: `#${cid}`, type: 'cluster',
            size: 4, color: CLUSTER_COLOR,
            x: 0, y: 0, vx: 0, vy: 0,
          })
        }
        links.push({ from: ideaKey, to: clKey })
      })
    })

    return { nodes, links }
  }, [ideas])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || nodes.length === 0) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const dpr = 2
    const W = canvas.offsetWidth * dpr
    const H = 500 * dpr
    canvas.width = W
    canvas.height = H
    canvas.style.height = '500px'

    // Init positions randomly
    nodes.forEach(n => {
      n.x = W / 2 + (Math.random() - 0.5) * W * 0.6
      n.y = H / 2 + (Math.random() - 0.5) * H * 0.6
      n.vx = 0
      n.vy = 0
    })

    const nodeMap = new Map(nodes.map(n => [n.id, n]))

    function tick() {
      // Reset velocities
      nodes.forEach(n => { n.vx = 0; n.vy = 0 })

      // Repulsion between all nodes
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const a = nodes[i], b = nodes[j]
          let dx = b.x - a.x, dy = b.y - a.y
          const dist = Math.sqrt(dx * dx + dy * dy) || 1
          const force = 800 / (dist * dist)
          const fx = (dx / dist) * force
          const fy = (dy / dist) * force
          a.vx -= fx; a.vy -= fy
          b.vx += fx; b.vy += fy
        }
      }

      // Attraction along links
      links.forEach(l => {
        const a = nodeMap.get(l.from), b = nodeMap.get(l.to)
        if (!a || !b) return
        const dx = b.x - a.x, dy = b.y - a.y
        const dist = Math.sqrt(dx * dx + dy * dy) || 1
        const targetDist = 120 * dpr
        const force = (dist - targetDist) * 0.005
        const fx = (dx / dist) * force
        const fy = (dy / dist) * force
        a.vx += fx; a.vy += fy
        b.vx -= fx; b.vy -= fy
      })

      // Center gravity
      nodes.forEach(n => {
        n.vx += (W / 2 - n.x) * 0.0005
        n.vy += (H / 2 - n.y) * 0.0005
      })

      // Apply velocities with damping
      nodes.forEach(n => {
        n.x += n.vx * 0.4
        n.y += n.vy * 0.4
        // Keep in bounds
        const margin = 40 * dpr
        n.x = Math.max(margin, Math.min(W - margin, n.x))
        n.y = Math.max(margin, Math.min(H - margin, n.y))
      })
    }

    function draw() {
      ctx!.clearRect(0, 0, W, H)

      // Draw links
      links.forEach(l => {
        const a = nodeMap.get(l.from), b = nodeMap.get(l.to)
        if (!a || !b) return
        const isHighlighted = hovered === a.id || hovered === b.id
        ctx!.beginPath()
        ctx!.moveTo(a.x, a.y)
        ctx!.lineTo(b.x, b.y)
        ctx!.strokeStyle = isHighlighted ? 'rgba(255,255,255,0.25)' : LINK_COLOR
        ctx!.lineWidth = isHighlighted ? 2 : 1
        ctx!.stroke()
      })

      // Draw nodes
      nodes.forEach(n => {
        const isHov = hovered === n.id
        const r = n.size * dpr * (isHov ? 1.3 : 1)

        // Glow
        if (isHov) {
          ctx!.beginPath()
          ctx!.arc(n.x, n.y, r + 8, 0, Math.PI * 2)
          ctx!.fillStyle = n.color + '22'
          ctx!.fill()
        }

        // Node circle
        ctx!.beginPath()
        ctx!.arc(n.x, n.y, r, 0, Math.PI * 2)
        ctx!.fillStyle = isHov ? n.color : n.color + 'cc'
        ctx!.fill()

        // Label
        const fontSize = n.type === 'idea' ? Math.max(18, n.size * 1.5) : 14
        ctx!.font = `${n.type === 'idea' ? 'bold ' : ''}${fontSize}px system-ui`
        ctx!.fillStyle = isHov ? '#fff' : 'rgba(255,255,255,0.7)'
        ctx!.textAlign = 'center'
        ctx!.textBaseline = 'top'
        const label = n.label.length > 20 ? n.label.slice(0, 19) + '…' : n.label
        ctx!.fillText(label, n.x, n.y + r + 4)
      })
    }

    // Run simulation
    let frame = 0
    function animate() {
      tick()
      draw()
      frame++
      if (frame < 300) {
        animRef.current = requestAnimationFrame(animate)
      }
    }
    animate()

    // Mouse hover
    const handleMove = (e: MouseEvent) => {
      const rect = canvas.getBoundingClientRect()
      const mx = (e.clientX - rect.left) * dpr
      const my = (e.clientY - rect.top) * dpr
      let found: string | null = null
      for (const n of nodes) {
        const dx = mx - n.x, dy = my - n.y
        const r = n.size * dpr * 1.5
        if (dx * dx + dy * dy <= r * r) {
          found = n.id
          break
        }
      }
      setHovered(found)
      canvas.style.cursor = found ? 'pointer' : 'default'
      draw()
    }

    const handleClick = (e: MouseEvent) => {
      const rect = canvas.getBoundingClientRect()
      const mx = (e.clientX - rect.left) * dpr
      const my = (e.clientY - rect.top) * dpr
      for (const n of nodes) {
        if (!n.sourceId) continue
        const dx = mx - n.x, dy = my - n.y
        const r = n.size * dpr * 1.5
        if (dx * dx + dy * dy <= r * r) {
          onSelect(n.sourceId)
          break
        }
      }
    }

    canvas.addEventListener('mousemove', handleMove)
    canvas.addEventListener('click', handleClick)
    return () => {
      cancelAnimationFrame(animRef.current)
      canvas.removeEventListener('mousemove', handleMove)
      canvas.removeEventListener('click', handleClick)
    }
  }, [nodes, links, hovered, onSelect])

  return (
    <div>
      <canvas ref={canvasRef} className="w-full rounded-xl bg-gray-950 border border-gray-800" />
      <div className="flex gap-4 mt-2 text-xs text-gray-500 justify-center">
        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full" style={{ background: IDEA_COLOR }} /> Идеи</span>
        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full" style={{ background: CLUSTER_COLOR }} /> Кластеры болей</span>
        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full" style={{ background: SUB_COLOR }} /> Сабреддиты</span>
      </div>
    </div>
  )
}
