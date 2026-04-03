import { useEffect, useRef, useMemo } from 'react'

interface Idea {
  id: number
  title: string
  score: number
  subreddits: string
}

interface Props {
  ideas: Idea[]
  onSelect: (id: number) => void
}

const COLORS = ['#818cf8', '#a78bfa', '#c084fc', '#e879f9', '#f472b6', '#fb7185', '#f87171', '#fb923c', '#fbbf24', '#a3e635']

export default function BubbleChart({ ideas, onSelect }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  const bubbles = useMemo(() => {
    const subColors: Record<string, string> = {}
    let colorIdx = 0
    return ideas.map(idea => {
      let firstSub = ''
      try { firstSub = JSON.parse(idea.subreddits)?.[0] || '' } catch {}
      if (firstSub && !subColors[firstSub]) {
        subColors[firstSub] = COLORS[colorIdx % COLORS.length]
        colorIdx++
      }
      const r = Math.max(25, Math.min(60, idea.score * 7))
      return { ...idea, r, color: subColors[firstSub] || COLORS[0], x: 0, y: 0 }
    })
  }, [ideas])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || bubbles.length === 0) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const W = canvas.width = canvas.offsetWidth * 2
    const H = canvas.height = 400 * 2
    canvas.style.height = '400px'

    // Simple circle packing
    bubbles.forEach((b, i) => {
      const angle = (i / bubbles.length) * Math.PI * 2
      const dist = 80 + i * 15
      b.x = W / 2 + Math.cos(angle) * dist
      b.y = H / 2 + Math.sin(angle) * dist
    })

    // Simple force simulation
    for (let iter = 0; iter < 100; iter++) {
      for (let i = 0; i < bubbles.length; i++) {
        for (let j = i + 1; j < bubbles.length; j++) {
          const dx = bubbles[j].x - bubbles[i].x
          const dy = bubbles[j].y - bubbles[i].y
          const dist = Math.sqrt(dx * dx + dy * dy)
          const minDist = (bubbles[i].r + bubbles[j].r) * 2 + 8
          if (dist < minDist && dist > 0) {
            const force = (minDist - dist) / dist * 0.3
            bubbles[i].x -= dx * force
            bubbles[i].y -= dy * force
            bubbles[j].x += dx * force
            bubbles[j].y += dy * force
          }
        }
        // Pull toward center
        bubbles[i].x += (W / 2 - bubbles[i].x) * 0.01
        bubbles[i].y += (H / 2 - bubbles[i].y) * 0.01
      }
    }

    // Draw
    ctx.clearRect(0, 0, W, H)
    bubbles.forEach(b => {
      ctx.beginPath()
      ctx.arc(b.x, b.y, b.r * 2, 0, Math.PI * 2)
      ctx.fillStyle = b.color + '33'
      ctx.fill()
      ctx.strokeStyle = b.color
      ctx.lineWidth = 2
      ctx.stroke()

      ctx.fillStyle = '#fff'
      ctx.font = `bold ${Math.max(16, b.r * 0.6)}px system-ui`
      ctx.textAlign = 'center'
      ctx.textBaseline = 'middle'
      const label = b.title.length > 15 ? b.title.slice(0, 14) + '…' : b.title
      ctx.fillText(label, b.x, b.y - 8)
      ctx.font = `${Math.max(14, b.r * 0.5)}px system-ui`
      ctx.fillStyle = b.color
      ctx.fillText(`${b.score}/10`, b.x, b.y + 14)
    })

    // Click handler
    const handleClick = (e: MouseEvent) => {
      const rect = canvas.getBoundingClientRect()
      const mx = (e.clientX - rect.left) * 2
      const my = (e.clientY - rect.top) * 2
      for (const b of bubbles) {
        const dx = mx - b.x, dy = my - b.y
        if (dx * dx + dy * dy <= (b.r * 2) ** 2) {
          onSelect(b.id)
          break
        }
      }
    }
    canvas.addEventListener('click', handleClick)
    return () => canvas.removeEventListener('click', handleClick)
  }, [bubbles, onSelect])

  return <canvas ref={canvasRef} className="w-full rounded-xl bg-gray-900" />
}
