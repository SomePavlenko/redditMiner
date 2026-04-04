import { useState, useEffect, useMemo } from 'react'
import { useParams, Link } from 'react-router-dom'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
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
  feasibility_breakdown: string
}

interface Cluster {
  id: number
  cluster_name: string
  summary: string
  pain_score: number
  frequency: number
  subreddit_spread: number
  problems_json: string
}

interface Problem {
  id: number
  problem: string
  subreddit: string
  upvotes: number
  source_url: string
}

const competitionConfig: Record<string, { label: string; class: string; desc: string }> = {
  none:   { label: 'Нет рынка',    class: 'bg-yellow-900/30 text-yellow-400 border-yellow-800', desc: 'Потенциально нет спроса — рынок не доказан' },
  low:    { label: 'Слабая',       class: 'bg-yellow-900/20 text-yellow-300 border-yellow-800', desc: 'Мало конкурентов — спрос возможен, но не доказан' },
  medium: { label: 'Умеренная',    class: 'bg-green-900/30 text-green-400 border-green-800',    desc: 'Конкуренты есть = спрос доказан, есть место для дифференциации' },
  high:   { label: 'Высокая',     class: 'bg-red-900/30 text-red-400 border-red-800',          desc: 'Много конкурентов — нужен сильный уникальный угол' },
}

function ScoreBar({ label, value, max = 10 }: { label: string; value: number; max?: number }) {
  const pct = Math.min(Math.max((value || 0) / max, 0), 1) * 100
  const color = value >= 7 ? 'bg-green-500' : value >= 5 ? 'bg-yellow-500' : 'bg-red-500'
  return (
    <div className="flex items-center gap-3">
      <span className="text-sm text-gray-400 w-40 shrink-0">{label}</span>
      <div className="h-2 flex-1 rounded-full bg-gray-800 overflow-hidden">
        <div className={cn('h-full rounded-full', color)} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-sm font-mono text-gray-300 w-8 text-right">{value || 0}</span>
    </div>
  )
}

export default function IdeaDetail() {
  const { id } = useParams<{ id: string }>()
  const [idea, setIdea] = useState<Idea | null>(null)
  const [clusters, setClusters] = useState<Cluster[]>([])
  const [relatedProblems, setRelatedProblems] = useState<Problem[]>([])
  const [analyzing, setAnalyzing] = useState(false)
  const [showAllProblems, setShowAllProblems] = useState(false)

  useEffect(() => {
    fetch(`/api/ideas?show_duplicates=1&limit=1000`)
      .then(r => r.json())
      .then((data) => {
        const items: Idea[] = data.items || data || []
        const found = items.find(i => i.id === Number(id))
        if (found) setIdea(found)
      })
      .catch(() => {})

    fetch('/api/clusters')
      .then(r => r.json())
      .then(setClusters)
      .catch(() => {})

    fetch('/api/problems?limit=500')
      .then(r => r.json())
      .then(setRelatedProblems)
      .catch(() => {})
  }, [id])

  const solvedClusterIds = useMemo(() => {
    if (!idea?.solves_clusters) return []
    try { return JSON.parse(idea.solves_clusters) as number[] } catch { return [] }
  }, [idea?.solves_clusters])

  const solvedClusters = useMemo(() =>
    clusters.filter(c => solvedClusterIds.includes(c.id)),
  [clusters, solvedClusterIds])

  const clusterProblems = useMemo(() => {
    const problemIds = new Set<number>()
    solvedClusters.forEach(c => {
      try {
        const ids = JSON.parse(c.problems_json || '[]') as number[]
        ids.forEach(id => problemIds.add(id))
      } catch { /* ignore */ }
    })
    return relatedProblems.filter(p => problemIds.has(p.id))
  }, [solvedClusters, relatedProblems])

  const subs = useMemo(() => {
    if (!idea?.subreddits) return []
    try { return JSON.parse(idea.subreddits) as string[] } catch { return [] }
  }, [idea?.subreddits])

  const fb = useMemo(() => {
    if (!idea?.feasibility_breakdown) return null
    try { return JSON.parse(idea.feasibility_breakdown) } catch { return null }
  }, [idea?.feasibility_breakdown])

  const comp = idea ? competitionConfig[idea.competition_level] : null

  const runDeepAnalysis = async () => {
    if (!idea) return
    setAnalyzing(true)
    try {
      const resp = await fetch(`/api/ideas/${idea.id}/deep-analysis`, { method: 'POST' })
      const data = await resp.json()
      if (data.result) {
        setIdea({
          ...idea,
          deep_analysis_result: data.result,
          deep_analysis_done: 1,
          // Update scores from deep analysis
          ...(data.new_score != null ? { score: data.new_score } : {}),
          ...(data.feasibility_score != null ? { feasibility_score: data.feasibility_score } : {}),
          ...(data.uniqueness_score != null ? { uniqueness_score: data.uniqueness_score } : {}),
          ...(data.competition_level ? { competition_level: data.competition_level } : {}),
        })
      }
    } catch { /* ignore */ }
    setAnalyzing(false)
  }

  const toggleFav = async () => {
    if (!idea) return
    await fetch(`/api/ideas/${idea.id}/favourite`, { method: 'POST' })
    setIdea({ ...idea, is_favourite: idea.is_favourite ? 0 : 1 })
  }

  if (!idea) return <div className="text-gray-500 text-center py-12">Загрузка...</div>

  const visibleProblems = showAllProblems ? clusterProblems : clusterProblems.slice(0, 5)

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Back link */}
      <Link to="/ideas" className="text-sm text-gray-500 hover:text-gray-300">← Все идеи</Link>

      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white">{idea.title}</h1>
          <p className="text-gray-400 text-sm mt-1">{idea.created_at?.split('T')[0] || idea.created_at?.split(' ')[0]}</p>
        </div>
        <div className="flex items-center gap-3">
          <span className={cn(
            'text-2xl font-bold',
            idea.score >= 7 ? 'text-green-400' : idea.score >= 5 ? 'text-yellow-400' : 'text-gray-400'
          )}>{idea.score}/10</span>
          <button onClick={toggleFav} className={cn('text-2xl', idea.is_favourite ? 'text-yellow-400' : 'text-gray-600 hover:text-yellow-400')}>★</button>
        </div>
      </div>

      {/* Main info */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left column — idea details */}
        <div className="lg:col-span-2 space-y-4">
          {idea.pain && (
            <Card className="bg-gray-900 border-gray-800">
              <CardContent className="p-5 space-y-3">
                <div>
                  <span className="text-xs text-gray-500 uppercase tracking-wide">Боль</span>
                  <p className="text-gray-200 mt-1">{idea.pain}</p>
                </div>
                <div>
                  <span className="text-xs text-gray-500 uppercase tracking-wide">Решение</span>
                  <p className="text-gray-200 mt-1">{idea.solution}</p>
                </div>
              </CardContent>
            </Card>
          )}

          {idea.where_we_meet_user && (
            <Card className="bg-indigo-950/20 border-indigo-900/50">
              <CardContent className="p-5">
                <span className="text-xs text-indigo-400 uppercase tracking-wide">Где встречаем пользователя</span>
                <p className="text-indigo-200 mt-1">{idea.where_we_meet_user}</p>
              </CardContent>
            </Card>
          )}

          {/* Monetization + Competition */}
          <div className="grid grid-cols-2 gap-4">
            {idea.monetization && (
              <Card className="bg-gray-900 border-gray-800">
                <CardContent className="p-5">
                  <span className="text-xs text-gray-500 uppercase tracking-wide">Монетизация</span>
                  <p className="text-gray-200 mt-1">{idea.monetization}</p>
                  {idea.monetization_type && (
                    <Badge variant="outline" className="mt-2 bg-gray-800 text-gray-400 border-gray-700 text-[11px]">
                      {idea.monetization_type}
                    </Badge>
                  )}
                </CardContent>
              </Card>
            )}
            {comp && (
              <Card className="bg-gray-900 border-gray-800">
                <CardContent className="p-5">
                  <span className="text-xs text-gray-500 uppercase tracking-wide">Конкуренция</span>
                  <Badge variant="outline" className={cn('mt-1 block w-fit', comp.class)}>{comp.label}</Badge>
                  <p className="text-xs text-gray-500 mt-2">{comp.desc}</p>
                  {idea.competition_note && <p className="text-gray-300 text-sm mt-2">{idea.competition_note}</p>}
                </CardContent>
              </Card>
            )}
          </div>

          {idea.validation_step && (
            <Card className="bg-green-950/20 border-green-900/50">
              <CardContent className="p-5">
                <span className="text-xs text-green-400 uppercase tracking-wide">Первый шаг валидации (48 часов)</span>
                <p className="text-green-200 mt-1">{idea.validation_step}</p>
              </CardContent>
            </Card>
          )}

          {/* Fallback for old ideas */}
          {!idea.pain && idea.description && (
            <Card className="bg-gray-900 border-gray-800">
              <CardContent className="p-5">
                <p className="text-gray-200">{idea.description}</p>
                {idea.product_example && <p className="text-gray-500 mt-2 italic">→ {idea.product_example}</p>}
              </CardContent>
            </Card>
          )}

          {/* Deep Analysis */}
          <Card className="bg-gray-900 border-gray-800">
            <CardHeader className="px-5 pt-5 pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-base text-white">Deep Analysis</CardTitle>
                {idea.deep_analysis_done ? (
                  <Badge variant="outline" className="bg-green-900/20 text-green-400 border-green-800 text-[10px]">
                    Оценки обновлены
                  </Badge>
                ) : null}
              </div>
            </CardHeader>
            <CardContent className="px-5 pb-5">
              {idea.deep_analysis_result ? (
                <div className="text-sm text-gray-300 whitespace-pre-wrap bg-gray-950 border border-gray-800 rounded-lg p-4 max-h-[600px] overflow-y-auto">
                  {idea.deep_analysis_result}
                </div>
              ) : analyzing ? (
                <div className="space-y-3">
                  <div className="flex items-center gap-3">
                    <div className="w-4 h-4 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
                    <span className="text-sm text-gray-400">Анализирую конкурентов, рынок, MVP стек...</span>
                  </div>
                  <div className="h-1 w-full bg-gray-800 rounded-full overflow-hidden">
                    <div className="h-full bg-indigo-500 rounded-full animate-pulse" style={{ width: '60%' }} />
                  </div>
                  <p className="text-xs text-gray-600">Обычно 30-60 секунд. Оценки обновятся автоматически.</p>
                </div>
              ) : (
                <Button
                  variant="outline"
                  className="w-full bg-gray-800 border-gray-700 hover:bg-gray-700"
                  onClick={runDeepAnalysis}
                >
                  Запустить Deep Analysis
                </Button>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Right column — scores + clusters + problems */}
        <div className="space-y-4">
          {/* Scores */}
          <Card className="bg-gray-900 border-gray-800">
            <CardHeader className="px-5 pt-5 pb-3">
              <CardTitle className="text-base">Оценки</CardTitle>
            </CardHeader>
            <CardContent className="px-5 pb-5 space-y-2">
              <ScoreBar label="Спрос" value={idea.demand_score} />
              <ScoreBar label="Широта покрытия" value={idea.breadth_score} />
              <ScoreBar label="Реализуемость" value={idea.feasibility_score} />
              <ScoreBar label="Уникальность" value={idea.uniqueness_score} />

              {fb && (
                <>
                  <Separator className="my-3 bg-gray-800" />
                  <p className="text-xs text-gray-500 uppercase tracking-wide mb-2">Breakdown реализуемости</p>
                  <ScoreBar label="Техническая сложность" value={fb.tech_complexity} />
                  <ScoreBar label="Доступность данных" value={fb.data_availability} />
                  <ScoreBar label="Внешние зависимости" value={fb.third_party_deps} />
                  <ScoreBar label="Юридические риски" value={fb.legal_risk} />
                  {fb.mvp_scope && (
                    <p className="text-xs text-gray-400 mt-2 italic">{fb.mvp_scope}</p>
                  )}
                </>
              )}
            </CardContent>
          </Card>

          {/* Related clusters */}
          {solvedClusters.length > 0 && (
            <Card className="bg-gray-900 border-gray-800">
              <CardHeader className="px-5 pt-5 pb-3">
                <CardTitle className="text-base">Решает кластеры болей</CardTitle>
              </CardHeader>
              <CardContent className="px-5 pb-5 space-y-2">
                {solvedClusters.map(c => (
                  <div key={c.id} className="bg-gray-800/50 rounded-lg p-3">
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium text-pink-300">{c.cluster_name}</span>
                      <Badge variant="outline" className="text-[10px] bg-pink-900/20 text-pink-400 border-pink-800">
                        {c.pain_score.toFixed(1)}
                      </Badge>
                    </div>
                    <p className="text-xs text-gray-400 mt-1">{c.summary}</p>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          {/* Related problems (pains behind this idea) */}
          {clusterProblems.length > 0 && (
            <Card className="bg-gray-900 border-gray-800">
              <CardHeader className="px-5 pt-5 pb-3">
                <CardTitle className="text-base">Боли пользователей ({clusterProblems.length})</CardTitle>
              </CardHeader>
              <CardContent className="px-5 pb-5 space-y-2">
                {visibleProblems.map(p => (
                  <div key={p.id} className="text-xs text-gray-400 border-l-2 border-gray-700 pl-2 py-1">
                    <span className="text-gray-300">{p.problem}</span>
                    <span className="text-gray-600 ml-2">r/{p.subreddit} · ↑{p.upvotes}</span>
                  </div>
                ))}
                {clusterProblems.length > 5 && (
                  <button
                    onClick={() => setShowAllProblems(!showAllProblems)}
                    className="text-xs text-indigo-400 hover:text-indigo-300"
                  >
                    {showAllProblems ? 'Скрыть' : `Показать все (${clusterProblems.length})`}
                  </button>
                )}
              </CardContent>
            </Card>
          )}

          {/* Subreddits */}
          {subs.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {subs.map(s => (
                <Badge key={s} variant="outline" className="bg-gray-800/60 text-gray-400 border-gray-700 text-[11px]">
                  r/{s}
                </Badge>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
