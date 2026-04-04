import { useState, useEffect, useCallback } from 'react'
import IdeaCard from '../components/IdeaCard'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { Button } from '@/components/ui/button'

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

interface Sub {
  name: string
  weight: number
  total_ideas: number
  last_parsed_at: string
  queue_reparse: number
}

interface Cluster {
  cluster_name: string
  pain_score: number
  frequency: number
}

export default function Ideas() {
  const [ideas, setIdeas] = useState<Idea[]>([])
  const [subs, setSubs] = useState<Sub[]>([])
  const [clusters, setClusters] = useState<Cluster[]>([])
  const [filters, setFilters] = useState({
    subreddit: '',
    favourite: undefined as number | undefined,
    min_score: undefined as number | undefined,
    sort: 'score' as 'score' | 'date' | 'favourite',
  })
  const [page, setPage] = useState(0)

  const fetchIdeas = useCallback(() => {
    const params = new URLSearchParams()
    if (filters.subreddit) params.set('subreddit', filters.subreddit)
    if (filters.favourite !== undefined) params.set('favourite', String(filters.favourite))
    if (filters.min_score !== undefined) params.set('min_score', String(filters.min_score))
    params.set('limit', '20')
    params.set('offset', String(page * 20))
    fetch(`/api/ideas?${params}`)
      .then(r => r.json())
      .then(data => {
        if (filters.sort === 'date') data.sort((a: Idea, b: Idea) => (b.created_at || '').localeCompare(a.created_at || ''))
        else if (filters.sort === 'favourite') data.sort((a: Idea, b: Idea) => b.is_favourite - a.is_favourite)
        setIdeas(data)
      })
      .catch(() => {})
  }, [filters, page])

  useEffect(() => { fetchIdeas() }, [fetchIdeas])

  useEffect(() => {
    fetch('/api/subreddits').then(r => r.json()).then(setSubs).catch(() => {})
    fetch('/api/clusters').then(r => r.json()).then((data: Cluster[]) => {
      setClusters([...data].sort((a, b) => b.pain_score - a.pain_score))
    }).catch(() => {})
  }, [])

  const toggleFav = async (id: number) => {
    await fetch(`/api/ideas/${id}/favourite`, { method: 'POST' })
    fetchIdeas()
  }

  const queueSub = async (name: string) => {
    await fetch(`/api/subreddits/${name}/queue`, { method: 'POST' })
    const resp = await fetch('/api/subreddits')
    setSubs(await resp.json())
  }

  const maxWeight = Math.max(...subs.map(s => s.weight), 1)
  const maxPainScore = Math.max(...clusters.map(c => c.pain_score), 1)

  return (
    <div className="flex gap-6 min-h-0">
      {/* ── Left panel 70% ── */}
      <div className="flex-[7] min-w-0 flex flex-col gap-4">
        <h1 className="text-2xl font-bold text-white">Все идеи</h1>

        {/* Filter row */}
        <div className="flex gap-2 flex-wrap items-center">
          <select
            value={filters.subreddit}
            onChange={e => { setFilters(f => ({ ...f, subreddit: e.target.value })); setPage(0) }}
            className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-gray-200 focus:outline-none focus:ring-1 focus:ring-indigo-500 cursor-pointer"
          >
            <option value="">Все сабреддиты</option>
            {subs.map(s => <option key={s.name} value={s.name}>r/{s.name}</option>)}
          </select>

          <select
            value={filters.favourite ?? ''}
            onChange={e => { setFilters(f => ({ ...f, favourite: e.target.value ? Number(e.target.value) : undefined })); setPage(0) }}
            className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-gray-200 focus:outline-none focus:ring-1 focus:ring-indigo-500 cursor-pointer"
          >
            <option value="">Все</option>
            <option value="1">★ Избранные</option>
          </select>

          <select
            value={filters.min_score ?? ''}
            onChange={e => { setFilters(f => ({ ...f, min_score: e.target.value ? Number(e.target.value) : undefined })); setPage(0) }}
            className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-gray-200 focus:outline-none focus:ring-1 focus:ring-indigo-500 cursor-pointer"
          >
            <option value="">Любой score</option>
            <option value="6">6+</option>
            <option value="7">7+</option>
            <option value="8">8+</option>
          </select>

          <select
            value={filters.sort}
            onChange={e => setFilters(f => ({ ...f, sort: e.target.value as typeof f.sort }))}
            className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-gray-200 focus:outline-none focus:ring-1 focus:ring-indigo-500 cursor-pointer"
          >
            <option value="score">По score</option>
            <option value="date">По дате</option>
            <option value="favourite">По избранным</option>
          </select>

          {(filters.subreddit || filters.favourite !== undefined || filters.min_score !== undefined) && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => { setFilters({ subreddit: '', favourite: undefined, min_score: undefined, sort: filters.sort }); setPage(0) }}
              className="text-gray-500 hover:text-gray-300 text-xs px-2"
            >
              Сбросить
            </Button>
          )}
        </div>

        {/* Ideas list */}
        <div className="flex flex-col gap-3">
          {ideas.map(idea => (
            <IdeaCard key={idea.id} idea={idea} onToggleFav={toggleFav} />
          ))}
          {ideas.length === 0 && (
            <div className="flex items-center justify-center py-20 text-gray-600 text-sm">
              Нет идей по выбранным фильтрам
            </div>
          )}
        </div>

        {/* Pagination */}
        <div className="flex items-center gap-2 justify-center pt-2 pb-6">
          <Button
            variant="outline"
            size="sm"
            disabled={page === 0}
            onClick={() => setPage(p => p - 1)}
            className="bg-gray-800 border-gray-700 text-gray-300 hover:bg-gray-700 hover:text-white disabled:opacity-30"
          >
            ← Назад
          </Button>
          <span className="px-3 py-1 text-xs text-gray-500 tabular-nums">
            Стр. {page + 1}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={ideas.length < 20}
            onClick={() => setPage(p => p + 1)}
            className="bg-gray-800 border-gray-700 text-gray-300 hover:bg-gray-700 hover:text-white disabled:opacity-30"
          >
            Вперёд →
          </Button>
        </div>
      </div>

      {/* ── Right panel 30% ── */}
      <div className="flex-[3] min-w-0 flex flex-col gap-4 max-w-xs">

        {/* Pain clusters */}
        <Card className="bg-gray-900 border-gray-800 gap-0 py-0">
          <CardHeader className="px-4 pt-4 pb-3">
            <CardTitle className="text-sm font-semibold text-white">
              Кластеры болей
            </CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-4 flex flex-col gap-3">
            {clusters.length === 0 && (
              <p className="text-xs text-gray-600">Нет данных</p>
            )}
            {clusters.map(cluster => (
              <div key={cluster.cluster_name} className="flex flex-col gap-1">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs text-gray-300 leading-snug flex-1 min-w-0 truncate">
                    {cluster.cluster_name}
                  </span>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <Badge
                      variant="outline"
                      className="bg-gray-800/60 border-gray-700 text-gray-400 text-[10px] font-normal h-auto py-0 px-1.5"
                    >
                      {cluster.frequency}
                    </Badge>
                    <span className="text-[10px] font-semibold tabular-nums text-gray-400 w-6 text-right">
                      {cluster.pain_score}
                    </span>
                  </div>
                </div>
                <div className="h-1 w-full rounded-full bg-gray-800 overflow-hidden">
                  <div
                    className="h-full rounded-full bg-rose-500/70 transition-all"
                    style={{ width: `${(cluster.pain_score / maxPainScore) * 100}%` }}
                  />
                </div>
              </div>
            ))}
          </CardContent>
        </Card>

        <Separator className="bg-gray-800" />

        {/* Subreddits */}
        <Card className="bg-gray-900 border-gray-800 gap-0 py-0">
          <CardHeader className="px-4 pt-4 pb-3">
            <CardTitle className="text-sm font-semibold text-white">
              Сабреддиты
            </CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-4 flex flex-col gap-3">
            {subs.map(sub => (
              <div key={sub.name} className="flex flex-col gap-1">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs font-medium text-gray-200">
                    r/{sub.name}
                  </span>
                  {sub.queue_reparse ? (
                    <Badge
                      variant="outline"
                      className="bg-orange-500/10 border-orange-700/50 text-orange-400 text-[10px] font-normal h-auto py-0 px-1.5"
                    >
                      В очереди
                    </Badge>
                  ) : (
                    <Button
                      variant="ghost"
                      size="xs"
                      onClick={() => queueSub(sub.name)}
                      className="text-gray-600 hover:text-gray-300 hover:bg-gray-800 text-[10px] h-5 px-1.5"
                    >
                      В очередь
                    </Button>
                  )}
                </div>
                <div className="h-1 w-full rounded-full bg-gray-800 overflow-hidden">
                  <div
                    className="h-full rounded-full bg-indigo-500 transition-all"
                    style={{ width: `${(sub.weight / maxWeight) * 100}%` }}
                  />
                </div>
                <div className="flex justify-between text-[10px] text-gray-600">
                  <span>{sub.total_ideas} идей</span>
                  <span>{sub.last_parsed_at?.split('T')[0] || '—'}</span>
                </div>
              </div>
            ))}
            {subs.length === 0 && (
              <p className="text-xs text-gray-600">Нет данных</p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
