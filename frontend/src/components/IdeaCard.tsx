import { useMemo } from 'react'
import { Link } from 'react-router-dom'
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
  pain: string
  solution: string
  where_we_meet_user: string
  monetization: string
  monetization_type: string
  competition_level: string
  competition_note: string
  validation_step: string
  deep_analysis_done: number
  deep_analysis_result: string
}

interface Props {
  idea: Idea
  onToggleFav: (id: number) => void
}

const competitionConfig: Record<string, { label: string; class: string }> = {
  none:   { label: 'нет рынка',  class: 'bg-yellow-900/30 text-yellow-400 border-yellow-800' },
  low:    { label: 'слабая',     class: 'bg-yellow-900/20 text-yellow-300 border-yellow-800' },
  medium: { label: 'умеренная',  class: 'bg-green-900/30 text-green-400 border-green-800' },
  high:   { label: 'высокая',   class: 'bg-red-900/30 text-red-400 border-red-800' },
}

function ScoreBadge({ score }: { score: number }) {
  const cls = score >= 7
    ? 'bg-green-600/20 text-green-400 border-green-700'
    : score >= 5
      ? 'bg-yellow-600/20 text-yellow-400 border-yellow-700'
      : 'bg-gray-700/40 text-gray-400 border-gray-600'
  return (
    <span className={cn('inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-bold tabular-nums', cls)}>
      {score}/10
    </span>
  )
}

function MiniBar({ label, value }: { label: string; value: number }) {
  const pct = Math.min(Math.max((value || 0) / 10, 0), 1) * 100
  const color = value >= 7 ? 'bg-green-500' : value >= 5 ? 'bg-yellow-500' : 'bg-gray-500'
  return (
    <div className="flex flex-col gap-1 min-w-0">
      <div className="flex justify-between items-center">
        <span className="text-[10px] text-gray-500 uppercase tracking-wide truncate">{label}</span>
        <span className="text-[10px] font-semibold text-gray-300 ml-1 tabular-nums">{value || 0}</span>
      </div>
      <div className="h-1 w-full rounded-full bg-gray-800 overflow-hidden">
        <div className={cn('h-full rounded-full', color)} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

export default function IdeaCard({ idea, onToggleFav }: Props) {
  const subs = useMemo(() => {
    try { return JSON.parse(idea.subreddits) as string[] } catch { return [] }
  }, [idea.subreddits])

  const comp = competitionConfig[idea.competition_level] || null

  return (
    <Card id={`idea-${idea.id}`} className="bg-gray-900 border-gray-800 hover:border-gray-700 transition-colors gap-0 py-0">
      <CardHeader className="px-5 pt-5 pb-0">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-2 min-w-0">
            <ScoreBadge score={idea.score} />
            <Link to={`/ideas/${idea.id}`} className="font-semibold text-white text-sm leading-snug hover:text-indigo-300 transition-colors">
              {idea.title}
            </Link>
          </div>
          <button
            onClick={(e) => { e.preventDefault(); onToggleFav(idea.id) }}
            className={cn('shrink-0 text-xl leading-none transition-colors',
              idea.is_favourite ? 'text-yellow-400' : 'text-gray-600 hover:text-yellow-400'
            )}
          >★</button>
        </div>
      </CardHeader>

      <CardContent className="px-5 pt-3 pb-0 flex flex-col gap-2.5">
        {/* Pain + Solution */}
        {idea.pain && (
          <div className="text-sm text-gray-300">
            <span className="font-medium text-gray-100">Боль: </span>{idea.pain}
          </div>
        )}
        {idea.solution && (
          <div className="text-sm text-gray-400">{idea.solution}</div>
        )}

        {/* Badges row: monetization + competition */}
        <div className="flex gap-2 flex-wrap">
          {idea.monetization && (
            <Badge variant="outline" className="bg-gray-800/60 text-gray-300 border-gray-700 text-[11px] font-normal h-auto py-0.5">
              {idea.monetization}
            </Badge>
          )}
          {comp && (
            <Badge variant="outline" className={cn('text-[11px] font-normal h-auto py-0.5', comp.class)}>
              {comp.label}
            </Badge>
          )}
          {idea.deep_analysis_done ? (
            <Badge variant="outline" className="bg-indigo-900/20 text-indigo-400 border-indigo-800 text-[11px] font-normal h-auto py-0.5">
              Deep Analysis ✓
            </Badge>
          ) : null}
        </div>

        {/* Fallback for old ideas */}
        {!idea.pain && idea.description && (
          <p className="text-gray-300 text-sm">{idea.description}</p>
        )}

        {/* Score breakdown */}
        <div className="grid grid-cols-4 gap-3">
          <MiniBar label="Спрос" value={idea.demand_score} />
          <MiniBar label="Широта" value={idea.breadth_score} />
          <MiniBar label="Реализуем." value={idea.feasibility_score} />
          <MiniBar label="Уникальн." value={idea.uniqueness_score} />
        </div>

        {/* Link to detail page */}
        <Link to={`/ideas/${idea.id}`} className="text-xs text-indigo-400 hover:text-indigo-300 text-center py-1">
          Подробнее →
        </Link>
      </CardContent>

      {subs.length > 0 && (
        <CardFooter className="px-5 py-3 mt-1 border-t border-gray-800 bg-transparent flex-wrap gap-1.5">
          {subs.map(s => (
            <Badge key={s} variant="outline" className="bg-gray-800/60 text-gray-400 border-gray-700 text-[11px] font-normal h-auto py-0.5">
              r/{s}
            </Badge>
          ))}
        </CardFooter>
      )}
    </Card>
  )
}
