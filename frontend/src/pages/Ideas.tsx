import { useState, useEffect, useCallback } from 'react'
import IdeaCard from '../components/IdeaCard'

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

export default function Ideas() {
  const [ideas, setIdeas] = useState<Idea[]>([])
  const [subs, setSubs] = useState<Sub[]>([])
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

  return (
    <div className="flex gap-6">
      <div className="flex-1 min-w-0">
        <h1 className="text-2xl font-bold mb-4">Все идеи</h1>
        <div className="flex gap-3 mb-4 flex-wrap">
          <select value={filters.subreddit} onChange={e => { setFilters(f => ({ ...f, subreddit: e.target.value })); setPage(0) }}
            className="bg-gray-800 rounded px-3 py-1.5 text-sm">
            <option value="">Все сабреддиты</option>
            {subs.map(s => <option key={s.name} value={s.name}>r/{s.name}</option>)}
          </select>
          <select value={filters.favourite ?? ''} onChange={e => { setFilters(f => ({ ...f, favourite: e.target.value ? Number(e.target.value) : undefined })); setPage(0) }}
            className="bg-gray-800 rounded px-3 py-1.5 text-sm">
            <option value="">Все</option>
            <option value="1">Избранные</option>
          </select>
          <select value={filters.min_score ?? ''} onChange={e => { setFilters(f => ({ ...f, min_score: e.target.value ? Number(e.target.value) : undefined })); setPage(0) }}
            className="bg-gray-800 rounded px-3 py-1.5 text-sm">
            <option value="">Любой score</option>
            <option value="6">6+</option>
            <option value="7">7+</option>
            <option value="8">8+</option>
          </select>
          <select value={filters.sort} onChange={e => setFilters(f => ({ ...f, sort: e.target.value as typeof f.sort }))}
            className="bg-gray-800 rounded px-3 py-1.5 text-sm">
            <option value="score">По score</option>
            <option value="date">По дате</option>
            <option value="favourite">По избранным</option>
          </select>
        </div>
        <div className="space-y-4">
          {ideas.map(idea => <IdeaCard key={idea.id} idea={idea} onToggleFav={toggleFav} />)}
          {ideas.length === 0 && <p className="text-gray-500 text-center py-12">Нет идей</p>}
        </div>
        <div className="flex gap-2 justify-center mt-6">
          <button disabled={page === 0} onClick={() => setPage(p => p - 1)}
            className="px-3 py-1 bg-gray-800 rounded disabled:opacity-30">← Назад</button>
          <span className="px-3 py-1 text-sm text-gray-400">Стр. {page + 1}</span>
          <button disabled={ideas.length < 20} onClick={() => setPage(p => p + 1)}
            className="px-3 py-1 bg-gray-800 rounded disabled:opacity-30">Вперёд →</button>
        </div>
      </div>

      <div className="w-72 shrink-0">
        <h2 className="text-lg font-semibold mb-3">Сабреддиты</h2>
        <div className="space-y-2">
          {subs.map(sub => (
            <div key={sub.name} className="bg-gray-900 rounded-lg p-3">
              <div className="flex items-center justify-between mb-1">
                <span className="text-sm font-medium">r/{sub.name}</span>
                {sub.queue_reparse ? (
                  <span className="w-2 h-2 rounded-full bg-orange-400" title="В очереди" />
                ) : (
                  <button onClick={() => queueSub(sub.name)}
                    className="text-xs text-gray-400 hover:text-white">В очередь</button>
                )}
              </div>
              <div className="w-full bg-gray-800 rounded-full h-1.5 mb-1">
                <div className="bg-indigo-500 h-1.5 rounded-full" style={{ width: `${(sub.weight / maxWeight) * 100}%` }} />
              </div>
              <div className="flex justify-between text-xs text-gray-500">
                <span>{sub.total_ideas} идей</span>
                <span>{sub.last_parsed_at?.split('T')[0] || '—'}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
