import { useMemo, useState } from 'react'
import { Card, CardHeader, CardContent, CardFooter } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
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
  const [analyzing, setAnalyzing] = useState(false)
  const [analysisResult, setAnalysisResult] = useState(idea.deep_analysis_result || '')
  const [analysisDone, setAnalysisDone] = useState(!!idea.deep_analysis_done)

  const subs = useMemo(() => {
    try { return JSON.parse(idea.subreddits) as string[] } catch { return [] }
  }, [idea.subreddits])

  const comp = competitionConfig[idea.competition_level] || null

  const runDeepAnalysis = async () => {
    setAnalyzing(true)
    try {
      const resp = await fetch(`/api/ideas/${idea.id}/deep-analysis`, { method: 'POST' })
      const data = await resp.json()
      if (data.result) {
        setAnalysisResult(data.result)
        setAnalysisDone(true)
      }
    } catch { /* ignore */ }
    setAnalyzing(false)
  }

  return (
    <Card id={`idea-${idea.id}`} className="bg-gray-900 border-gray-800 hover:border-gray-700 transition-colors gap-0 py-0">
      <CardHeader className="px-5 pt-5 pb-0">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-2 min-w-0">
            <ScoreBadge score={idea.score} />
            <h3 className="font-semibold text-white text-sm leading-snug">{idea.title}</h3>
          </div>
          <button
            onClick={() => onToggleFav(idea.id)}
            className={cn('shrink-0 text-xl leading-none transition-colors',
              idea.is_favourite ? 'text-yellow-400' : 'text-gray-600 hover:text-yellow-400'
            )}
          >★</button>
        </div>
      </CardHeader>

      <CardContent className="px-5 pt-3 pb-0 flex flex-col gap-3">
        {/* Боль */}
        {idea.pain && (
          <div className="text-sm text-gray-300">
            <span className="font-medium text-gray-100">Боль: </span>{idea.pain}
          </div>
        )}

        {/* Решение */}
        {idea.solution && (
          <div className="text-sm text-gray-300">
            <span className="font-medium text-gray-100">Решение: </span>{idea.solution}
          </div>
        )}

        {/* Где встречаем пользователя */}
        {idea.where_we_meet_user && (
          <div className="text-sm bg-indigo-950/30 border border-indigo-900/50 rounded-lg px-3 py-2">
            <span className="font-medium text-indigo-300">Где встречаем: </span>
            <span className="text-indigo-200">{idea.where_we_meet_user}</span>
          </div>
        )}

        {/* Монетизация + конкуренция */}
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
        </div>

        {/* Заметка о конкуренции */}
        {idea.competition_note && (
          <p className="text-xs text-gray-500 italic">{idea.competition_note}</p>
        )}

        {/* Первый шаг валидации */}
        {idea.validation_step && (
          <div className="text-sm border-l-2 border-green-700 pl-3">
            <span className="font-medium text-gray-100">Первый шаг: </span>
            <span className="text-gray-300">{idea.validation_step}</span>
          </div>
        )}

        {/* Fallback: старые поля если новых нет */}
        {!idea.pain && idea.description && (
          <p className="text-gray-300 text-sm">{idea.description}</p>
        )}
        {!idea.pain && idea.product_example && (
          <p className="text-gray-500 text-sm italic">→ {idea.product_example}</p>
        )}

        {/* Score breakdown */}
        <div className="grid grid-cols-4 gap-3">
          <MiniBar label="Спрос" value={idea.demand_score} />
          <MiniBar label="Широта" value={idea.breadth_score} />
          <MiniBar label="Реализуем." value={idea.feasibility_score} />
          <MiniBar label="Уникальн." value={idea.uniqueness_score} />
        </div>

        {/* Deep Analysis кнопка */}
        <Button
          variant="outline"
          size="sm"
          className={cn(
            'w-full text-xs',
            analysisDone
              ? 'bg-gray-800 text-gray-500 border-gray-700 cursor-default'
              : 'bg-gray-800 text-gray-300 border-gray-700 hover:bg-gray-700 hover:text-white'
          )}
          onClick={runDeepAnalysis}
          disabled={analysisDone || analyzing}
        >
          {analyzing ? 'Анализирую...' : analysisDone ? '✓ Deep Analysis выполнен' : 'Deep Analysis'}
        </Button>

        {/* Результат Deep Analysis */}
        {analysisResult && (
          <div className="text-sm bg-gray-950 border border-gray-800 rounded-lg p-3 text-gray-300 whitespace-pre-wrap max-h-96 overflow-y-auto">
            {analysisResult}
          </div>
        )}
      </CardContent>

      {/* Subreddit tags */}
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
