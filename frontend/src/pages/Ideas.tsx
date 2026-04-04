import { useState, useEffect, useCallback, useRef } from 'react'
import IdeaCard from '../components/IdeaCard'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'

interface Idea {
  id: number; title: string; description: string; product_example: string; score: number
  demand_score: number; breadth_score: number; feasibility_score: number; uniqueness_score: number
  revenue_model: string; solves_clusters: string; subreddits: string; source_urls: string
  is_favourite: number; created_at: string; pain: string; solution: string
  where_we_meet_user: string; monetization: string; monetization_type: string
  competition_level: string; competition_note: string; validation_step: string
  deep_analysis_done: number; deep_analysis_result: string
}

interface Sub { name: string; weight: number; total_ideas: number; last_parsed_at: string }

const PAGE_SIZE = 20

export default function Ideas() {
  const [ideas, setIdeas] = useState<Idea[]>([])
  const [total, setTotal] = useState(0)
  const [subs, setSubs] = useState<Sub[]>([])
  const [page, setPage] = useState(0)
  const [search, setSearch] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [filters, setFilters] = useState({
    favourite: undefined as number | undefined,
    min_score: undefined as number | undefined,
    sort: 'score' as 'score' | 'date' | 'favourite',
  })
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined)

  const fetchIdeas = useCallback(() => {
    const params = new URLSearchParams()
    if (search) params.set('search', search)
    if (filters.favourite !== undefined) params.set('favourite', String(filters.favourite))
    if (filters.min_score !== undefined) params.set('min_score', String(filters.min_score))
    params.set('sort', filters.sort)
    params.set('limit', String(PAGE_SIZE))
    params.set('offset', String(page * PAGE_SIZE))
    fetch(`/api/ideas?${params}`)
      .then(r => r.json())
      .then(data => {
        setIdeas(data.items || [])
        setTotal(data.total || 0)
      })
      .catch(() => {})
  }, [search, filters, page])

  useEffect(() => { fetchIdeas() }, [fetchIdeas])
  useEffect(() => { fetch('/api/subreddits').then(r => r.json()).then(setSubs).catch(() => {}) }, [])

  const handleSearchInput = (val: string) => {
    setSearchInput(val)
    clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => { setSearch(val); setPage(0) }, 300)
  }

  const toggleFav = async (id: number) => {
    await fetch(`/api/ideas/${id}/favourite`, { method: 'POST' })
    fetchIdeas()
  }

  const maxWeight = Math.max(...subs.map(s => s.weight), 1)
  const totalPages = Math.ceil(total / PAGE_SIZE)

  return (
    <div className="flex gap-6 min-h-0">
      <div className="flex-[7] min-w-0 flex flex-col gap-4">
        <h1 className="text-2xl font-bold text-white">Все идеи</h1>

        <div className="flex gap-2 flex-wrap items-center">
          <input
            value={searchInput}
            onChange={e => handleSearchInput(e.target.value)}
            placeholder="Поиск по названию, боли, решению..."
            className="flex-1 min-w-[200px] bg-gray-800 border border-gray-700 rounded-lg px-4 py-1.5 text-sm text-gray-200 focus:outline-none focus:ring-1 focus:ring-indigo-500 placeholder:text-gray-600"
          />

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
            <option value="5">5+</option>
            <option value="6">6+</option>
            <option value="7">7+</option>
          </select>

          <select
            value={filters.sort}
            onChange={e => { setFilters(f => ({ ...f, sort: e.target.value as typeof f.sort })); setPage(0) }}
            className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-gray-200 focus:outline-none focus:ring-1 focus:ring-indigo-500 cursor-pointer"
          >
            <option value="score">По score</option>
            <option value="date">По дате</option>
            <option value="favourite">По избранным</option>
          </select>

          {(search || filters.favourite !== undefined || filters.min_score !== undefined) && (
            <Button variant="ghost" size="sm"
              onClick={() => { setFilters({ favourite: undefined, min_score: undefined, sort: 'score' }); setSearch(''); setSearchInput(''); setPage(0) }}
              className="text-gray-500 hover:text-gray-300 text-xs px-2">
              Сбросить
            </Button>
          )}
        </div>

        <div className="text-xs text-gray-500">{total} идей</div>

        <div className="flex flex-col gap-3">
          {ideas.map(idea => <IdeaCard key={idea.id} idea={idea} onToggleFav={toggleFav} />)}
          {ideas.length === 0 && <div className="flex items-center justify-center py-20 text-gray-600 text-sm">Нет идей</div>}
        </div>

        {totalPages > 1 && (
          <div className="flex items-center gap-2 justify-center pt-2 pb-6">
            <Button variant="outline" size="sm" disabled={page === 0} onClick={() => setPage(p => p - 1)}
              className="bg-gray-800 border-gray-700 text-gray-300 hover:bg-gray-700 disabled:opacity-30">← Назад</Button>
            <span className="px-3 py-1 text-xs text-gray-500 tabular-nums">
              {page + 1} / {totalPages}
            </span>
            <Button variant="outline" size="sm" disabled={page >= totalPages - 1} onClick={() => setPage(p => p + 1)}
              className="bg-gray-800 border-gray-700 text-gray-300 hover:bg-gray-700 disabled:opacity-30">Вперёд →</Button>
          </div>
        )}
      </div>

      <div className="flex-[3] min-w-0 flex flex-col gap-4 max-w-xs">
        <Card className="bg-gray-900 border-gray-800 gap-0 py-0">
          <CardHeader className="px-4 pt-4 pb-3">
            <CardTitle className="text-sm font-semibold text-white">Сабреддиты</CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-4 flex flex-col gap-3">
            {subs.map(sub => (
              <div key={sub.name} className="flex flex-col gap-1">
                <span className="text-xs font-medium text-gray-200">r/{sub.name}</span>
                <div className="h-1 w-full rounded-full bg-gray-800 overflow-hidden">
                  <div className="h-full rounded-full bg-indigo-500" style={{ width: `${(sub.weight / maxWeight) * 100}%` }} />
                </div>
                <div className="flex justify-between text-[10px] text-gray-600">
                  <span>{sub.total_ideas} идей</span>
                  <span>{sub.last_parsed_at?.split('T')[0] || '—'}</span>
                </div>
              </div>
            ))}
            {subs.length === 0 && <p className="text-xs text-gray-600">Нет данных</p>}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
