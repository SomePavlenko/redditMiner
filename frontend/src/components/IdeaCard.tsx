import { useMemo } from 'react'
import { Card, CardHeader, CardContent, CardFooter } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

interface Idea {
  id: number
  title: string
  description: string
  product_example: string
  score: number
  demand_score: number
  breadth_score: number
  feasibility_score: number
  uniqueness_score: number
  revenue_model: string
  solves_clusters: string
  subreddits: string
  source_urls: string
  is_favourite: number
  created_at: string
}

interface Props {
  idea: Idea
  onToggleFav: (id: number) => void
}

function ScoreBadge({ score }: { score: number }) {
  const colorClass =
    score >= 7
      ? 'bg-green-600/20 text-green-400 border-green-700'
      : score >= 5
        ? 'bg-yellow-600/20 text-yellow-400 border-yellow-700'
        : 'bg-gray-700/40 text-gray-400 border-gray-600'

  return (
    <span
      className={cn(
        'inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-bold tabular-nums',
        colorClass
      )}
    >
      {score}/10
    </span>
  )
}

function MiniBar({ label, value }: { label: string; value: number }) {
  const pct = Math.min(Math.max(value / 10, 0), 1) * 100

  const barColor =
    value >= 7
      ? 'bg-green-500'
      : value >= 5
        ? 'bg-yellow-500'
        : 'bg-gray-500'

  return (
    <div className="flex flex-col gap-1 min-w-0">
      <div className="flex justify-between items-center">
        <span className="text-[10px] text-gray-500 uppercase tracking-wide truncate">{label}</span>
        <span className="text-[10px] font-semibold text-gray-300 ml-1 tabular-nums">{value}</span>
      </div>
      <div className="h-1 w-full rounded-full bg-gray-800 overflow-hidden">
        <div
          className={cn('h-full rounded-full transition-all', barColor)}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}

export default function IdeaCard({ idea, onToggleFav }: Props) {
  const subs = useMemo(() => {
    try {
      return JSON.parse(idea.subreddits) as string[]
    } catch {
      return []
    }
  }, [idea.subreddits])

  return (
    <Card
      id={`idea-${idea.id}`}
      className="bg-gray-900 border-gray-800 hover:border-gray-700 transition-colors gap-0 py-0"
    >
      {/* Header: score + title + favourite */}
      <CardHeader className="px-5 pt-5 pb-0">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-2 min-w-0">
            <ScoreBadge score={idea.score} />
            <h3 className="font-semibold text-white text-sm leading-snug">
              {idea.title}
            </h3>
          </div>
          <button
            onClick={() => onToggleFav(idea.id)}
            aria-label={idea.is_favourite ? 'Remove from favourites' : 'Add to favourites'}
            className={cn(
              'shrink-0 text-xl leading-none transition-colors',
              idea.is_favourite
                ? 'text-yellow-400'
                : 'text-gray-600 hover:text-yellow-400'
            )}
          >
            ★
          </button>
        </div>
      </CardHeader>

      {/* Body */}
      <CardContent className="px-5 pt-3 pb-0 flex flex-col gap-3">
        {/* Description */}
        <p className="text-gray-300 text-sm leading-relaxed">{idea.description}</p>

        {/* Product example */}
        {idea.product_example && (
          <p className="text-gray-500 text-sm italic">→ {idea.product_example}</p>
        )}

        {/* Revenue model badge */}
        {idea.revenue_model && (
          <div>
            <Badge
              variant="secondary"
              className="bg-gray-800 text-indigo-300 border-gray-700 text-[11px] font-normal h-auto py-0.5"
            >
              {idea.revenue_model}
            </Badge>
          </div>
        )}

        {/* Score breakdown */}
        <div className="grid grid-cols-4 gap-3">
          <MiniBar label="Спрос" value={idea.demand_score} />
          <MiniBar label="Широта" value={idea.breadth_score} />
          <MiniBar label="Реализуем." value={idea.feasibility_score} />
          <MiniBar label="Уникальн." value={idea.uniqueness_score} />
        </div>
      </CardContent>

      {/* Footer: subreddit tags */}
      {subs.length > 0 && (
        <CardFooter className="px-5 py-3 mt-1 border-t border-gray-800 bg-transparent flex-wrap gap-1.5">
          {subs.map((s) => (
            <Badge
              key={s}
              variant="outline"
              className="bg-gray-800/60 text-gray-400 border-gray-700 text-[11px] font-normal h-auto py-0.5"
            >
              r/{s}
            </Badge>
          ))}
        </CardFooter>
      )}
    </Card>
  )
}
