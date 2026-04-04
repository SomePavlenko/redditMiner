import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

interface Cluster {
  id: number
  cluster_name: string
  summary: string
  pain_score: number
  frequency: number
  subreddit_spread: number
  subreddits_json: string
  topic: string
}

export default function Problems() {
  const [clusters, setClusters] = useState<Cluster[]>([])
  const [topics, setTopics] = useState<string[]>([])
  const [filterTopic, setFilterTopic] = useState('')
  const [sortBy, setSortBy] = useState<'pain_score' | 'frequency' | 'subreddit_spread'>('pain_score')

  useEffect(() => {
    fetch('/api/clusters')
      .then(r => r.json())
      .then((data: Cluster[]) => {
        setClusters(data)
        const t = [...new Set(data.map(c => c.topic).filter(Boolean))]
        setTopics(t)
      })
      .catch(() => {})
  }, [])

  const filtered = clusters
    .filter(c => !filterTopic || c.topic === filterTopic)
    .sort((a, b) => (b[sortBy] ?? 0) - (a[sortBy] ?? 0))

  const maxScore = Math.max(...filtered.map(c => c.pain_score), 1)

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <h1 className="text-2xl font-bold text-white">Кластеры болей</h1>

      {/* Filters */}
      <div className="flex gap-3 flex-wrap">
        <select
          value={filterTopic}
          onChange={e => setFilterTopic(e.target.value)}
          className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-gray-200 focus:outline-none focus:ring-1 focus:ring-indigo-500"
        >
          <option value="">Все темы</option>
          {topics.map(t => <option key={t} value={t}>{t}</option>)}
        </select>

        <select
          value={sortBy}
          onChange={e => setSortBy(e.target.value as typeof sortBy)}
          className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-gray-200 focus:outline-none focus:ring-1 focus:ring-indigo-500"
        >
          <option value="pain_score">По pain score</option>
          <option value="frequency">По частоте</option>
          <option value="subreddit_spread">По охвату</option>
        </select>
      </div>

      {/* Cluster cards */}
      {filtered.length === 0 ? (
        <p className="text-gray-500 text-center py-12">Нет данных. Запустите прогон.</p>
      ) : (
        <div className="space-y-3">
          {filtered.map(cluster => {
            let subs: string[] = []
            try { subs = JSON.parse(cluster.subreddits_json || '[]') } catch { /* */ }

            return (
              <Link key={cluster.id} to={`/clusters/${cluster.id}`} className="block">
                <Card className="bg-gray-900 border-gray-800 hover:border-gray-700 transition-colors gap-0 py-0">
                  <CardContent className="p-5">
                    <div className="flex items-start justify-between gap-4">
                      <div className="min-w-0 flex-1">
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

                        {/* Pain score bar */}
                        <div className="h-1.5 w-full rounded-full bg-gray-800 overflow-hidden mb-3">
                          <div
                            className={cn('h-full rounded-full',
                              cluster.pain_score >= 25 ? 'bg-red-500' : cluster.pain_score >= 15 ? 'bg-yellow-500' : 'bg-gray-500'
                            )}
                            style={{ width: `${(cluster.pain_score / maxScore) * 100}%` }}
                          />
                        </div>

                        {/* Stats */}
                        <div className="flex gap-4 text-xs text-gray-500">
                          <span>Упоминаний: <b className="text-gray-300">{cluster.frequency}</b></span>
                          <span>Сабреддитов: <b className="text-gray-300">{cluster.subreddit_spread}</b></span>
                        </div>

                        {/* Subreddit tags */}
                        {subs.length > 0 && (
                          <div className="flex gap-1.5 flex-wrap mt-2">
                            {subs.map(s => (
                              <Badge key={s} variant="outline" className="bg-gray-800/60 text-gray-400 border-gray-700 text-[10px] font-normal h-auto py-0.5">
                                r/{s}
                              </Badge>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </Link>
            )
          })}
        </div>
      )}
    </div>
  )
}
