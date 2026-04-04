import { useState, useEffect, useCallback, useRef } from 'react'
import { Link } from 'react-router-dom'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

interface Cluster {
  id: number; cluster_name: string; summary: string; pain_score: number
  frequency: number; subreddit_spread: number; subreddits_json: string; topic: string
}

const PAGE_SIZE = 20

export default function Problems() {
  const [clusters, setClusters] = useState<Cluster[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(0)
  const [search, setSearch] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [sortBy, setSortBy] = useState<'pain_score' | 'frequency' | 'subreddit_spread'>('pain_score')
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined)

  const fetchClusters = useCallback(() => {
    const params = new URLSearchParams()
    if (search) params.set('search', search)
    params.set('sort', sortBy)
    params.set('limit', String(PAGE_SIZE))
    params.set('offset', String(page * PAGE_SIZE))
    fetch(`/api/clusters?${params}`)
      .then(r => r.json())
      .then(data => {
        setClusters(data.items || [])
        setTotal(data.total || 0)
      })
      .catch(() => {})
  }, [search, sortBy, page])

  useEffect(() => { fetchClusters() }, [fetchClusters])

  const handleSearchInput = (val: string) => {
    setSearchInput(val)
    clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => { setSearch(val); setPage(0) }, 300)
  }

  const maxScore = Math.max(...clusters.map(c => c.pain_score), 1)
  const totalPages = Math.ceil(total / PAGE_SIZE)

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <h1 className="text-2xl font-bold text-white">Кластеры болей</h1>

      <div className="flex gap-3 flex-wrap items-center">
        <input
          value={searchInput}
          onChange={e => handleSearchInput(e.target.value)}
          placeholder="Поиск по названию, описанию..."
          className="flex-1 min-w-[200px] bg-gray-800 border border-gray-700 rounded-lg px-4 py-1.5 text-sm text-gray-200 focus:outline-none focus:ring-1 focus:ring-indigo-500 placeholder:text-gray-600"
        />

        <select
          value={sortBy}
          onChange={e => { setSortBy(e.target.value as typeof sortBy); setPage(0) }}
          className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-gray-200 focus:outline-none focus:ring-1 focus:ring-indigo-500"
        >
          <option value="pain_score">По pain score</option>
          <option value="frequency">По частоте</option>
          <option value="subreddit_spread">По охвату</option>
        </select>

        {search && (
          <Button variant="ghost" size="sm"
            onClick={() => { setSearch(''); setSearchInput(''); setPage(0) }}
            className="text-gray-500 hover:text-gray-300 text-xs px-2">
            Сбросить
          </Button>
        )}
      </div>

      <div className="text-xs text-gray-500">{total} кластеров</div>

      {clusters.length === 0 ? (
        <p className="text-gray-500 text-center py-12">Нет данных</p>
      ) : (
        <div className="space-y-3">
          {clusters.map(cluster => {
            let subs: string[] = []
            try { subs = JSON.parse(cluster.subreddits_json || '[]') } catch { /* */ }

            return (
              <Link key={cluster.id} to={`/clusters/${cluster.id}`} className="block">
                <Card className="bg-gray-900 border-gray-800 hover:border-gray-700 transition-colors gap-0 py-0">
                  <CardContent className="p-5">
                    <div className="flex items-center gap-3 mb-2">
                      <Badge variant="outline" className={cn(
                        'text-xs font-bold px-2 py-0.5 tabular-nums shrink-0',
                        cluster.pain_score >= 25 ? 'bg-red-600/20 text-red-400 border-red-700' :
                        cluster.pain_score >= 15 ? 'bg-yellow-600/20 text-yellow-400 border-yellow-700' :
                        'bg-gray-700/40 text-gray-400 border-gray-600'
                      )}>
                        {cluster.pain_score.toFixed(1)}
                      </Badge>
                      <h3 className="font-semibold text-white text-sm">{cluster.cluster_name}</h3>
                    </div>
                    <p className="text-sm text-gray-400 mb-3">{cluster.summary}</p>
                    <div className="h-1.5 w-full rounded-full bg-gray-800 overflow-hidden mb-3">
                      <div className={cn('h-full rounded-full',
                        cluster.pain_score >= 25 ? 'bg-red-500' : cluster.pain_score >= 15 ? 'bg-yellow-500' : 'bg-gray-500'
                      )} style={{ width: `${(cluster.pain_score / maxScore) * 100}%` }} />
                    </div>
                    <div className="flex gap-4 text-xs text-gray-500">
                      <span>Упоминаний: <b className="text-gray-300">{cluster.frequency}</b></span>
                      <span>Сабреддитов: <b className="text-gray-300">{cluster.subreddit_spread}</b></span>
                    </div>
                    {subs.length > 0 && (
                      <div className="flex gap-1.5 flex-wrap mt-2">
                        {subs.map(s => (
                          <Badge key={s} variant="outline" className="bg-gray-800/60 text-gray-400 border-gray-700 text-[10px] font-normal h-auto py-0.5">r/{s}</Badge>
                        ))}
                      </div>
                    )}
                  </CardContent>
                </Card>
              </Link>
            )
          })}
        </div>
      )}

      {totalPages > 1 && (
        <div className="flex items-center gap-2 justify-center pt-2 pb-6">
          <Button variant="outline" size="sm" disabled={page === 0} onClick={() => setPage(p => p - 1)}
            className="bg-gray-800 border-gray-700 text-gray-300 hover:bg-gray-700 disabled:opacity-30">← Назад</Button>
          <span className="px-3 py-1 text-xs text-gray-500 tabular-nums">{page + 1} / {totalPages}</span>
          <Button variant="outline" size="sm" disabled={page >= totalPages - 1} onClick={() => setPage(p => p + 1)}
            className="bg-gray-800 border-gray-700 text-gray-300 hover:bg-gray-700 disabled:opacity-30">Вперёд →</Button>
        </div>
      )}
    </div>
  )
}
