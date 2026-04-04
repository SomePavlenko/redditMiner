import { useState, useEffect, useMemo } from 'react'
import { useParams, Link } from 'react-router-dom'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'

// ─── Types ────────────────────────────────────────────────────────────────────

interface Cluster {
  id: number
  cluster_name: string
  pain_score: number
  frequency: number
  subreddit_spread: number
  avg_upvotes?: number
  summary?: string
}

interface Problem {
  id: number
  problem: string
  subreddit: string
  upvotes: number
  source_url: string
  cluster_id?: number
}

interface Idea {
  id: number
  title: string
  score: number
  pain: string
  solves_clusters: string
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function painScoreColor(score: number) {
  if (score >= 7) return 'bg-red-500/15 text-red-400 border-red-800'
  if (score >= 4) return 'bg-yellow-500/15 text-yellow-400 border-yellow-800'
  return 'bg-green-500/15 text-green-400 border-green-800'
}

function ideaScoreColor(score: number) {
  if (score >= 7) return 'bg-green-500/15 text-green-400'
  if (score >= 5) return 'bg-yellow-500/15 text-yellow-400'
  return 'bg-gray-700/50 text-gray-400'
}

// ─── Main Component ───────────────────────────────────────────────────────────

export default function ClusterDetail() {
  const { id } = useParams<{ id: string }>()
  const numId = Number(id)

  const [cluster, setCluster] = useState<Cluster | null>(null)
  const [problems, setProblems] = useState<Problem[]>([])
  const [allIdeas, setAllIdeas] = useState<Idea[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)

    Promise.all([
      fetch('/api/clusters')
        .then(r => r.json())
        .then((clusters: Cluster[]) => {
          const found = clusters.find(c => c.id === numId)
          if (found) setCluster(found)
        }),
      fetch(`/api/problems?cluster_id=${numId}`)
        .then(r => r.json())
        .then((data: Problem[]) => setProblems(data))
        .catch(() => {}),
      fetch('/api/ideas?limit=1000')
        .then(r => r.json())
        .then((ideas: Idea[]) => setAllIdeas(ideas))
        .catch(() => {}),
    ])
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [numId])

  const clusterIdeas = useMemo(() => {
    return allIdeas
      .filter(idea => {
        if (!idea.solves_clusters) return false
        try {
          const ids = JSON.parse(idea.solves_clusters) as number[]
          return ids.includes(numId)
        } catch {
          return false
        }
      })
      .sort((a, b) => b.score - a.score)
  }, [allIdeas, numId])

  if (loading) {
    return <div className="text-gray-500 text-center py-12">Загрузка...</div>
  }

  if (!cluster) {
    return (
      <div className="max-w-4xl mx-auto space-y-4">
        <Link to="/trends" className="text-sm text-gray-500 hover:text-gray-300">← Все кластеры</Link>
        <p className="text-gray-500 text-center py-12">Кластер не найден</p>
      </div>
    )
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6 pb-12">
      {/* Back link */}
      <Link to="/trends" className="text-sm text-gray-500 hover:text-gray-300">
        ← Все кластеры
      </Link>

      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <h1 className="text-2xl font-bold text-white leading-snug">{cluster.cluster_name}</h1>
        <Badge
          variant="outline"
          className={`shrink-0 text-sm font-bold font-mono px-3 py-1 ${painScoreColor(cluster.pain_score)}`}
        >
          {cluster.pain_score.toFixed(1)}
        </Badge>
      </div>

      {/* Summary */}
      {cluster.summary && (
        <p className="text-gray-300 leading-relaxed">{cluster.summary}</p>
      )}

      {/* Stats row */}
      <div className="grid grid-cols-3 gap-4">
        <Card className="bg-gray-900 border-gray-800">
          <CardContent className="pt-5 pb-5 text-center">
            <p className="text-xs font-medium uppercase tracking-wider text-gray-500 mb-1">Frequency</p>
            <p className="text-3xl font-bold tabular-nums text-violet-400">
              {cluster.frequency?.toLocaleString() ?? '—'}
            </p>
          </CardContent>
        </Card>
        <Card className="bg-gray-900 border-gray-800">
          <CardContent className="pt-5 pb-5 text-center">
            <p className="text-xs font-medium uppercase tracking-wider text-gray-500 mb-1">Subreddits</p>
            <p className="text-3xl font-bold tabular-nums text-pink-400">
              {cluster.subreddit_spread ?? '—'}
            </p>
          </CardContent>
        </Card>
        <Card className="bg-gray-900 border-gray-800">
          <CardContent className="pt-5 pb-5 text-center">
            <p className="text-xs font-medium uppercase tracking-wider text-gray-500 mb-1">Avg upvotes</p>
            <p className="text-3xl font-bold tabular-nums text-amber-400">
              {cluster.avg_upvotes != null ? Math.round(cluster.avg_upvotes).toLocaleString() : '—'}
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Problems section */}
      <Card className="bg-gray-900 border-gray-800">
        <CardHeader>
          <CardTitle className="text-sm font-semibold text-gray-300 uppercase tracking-wider">
            Боли пользователей ({problems.length})
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {problems.length === 0 ? (
            <p className="text-gray-600 text-sm text-center py-4">Нет данных</p>
          ) : (
            problems.map(p => (
              <div
                key={p.id}
                className="border border-gray-800 rounded-lg p-4 space-y-2 bg-gray-800/20 hover:bg-gray-800/40 transition-colors"
              >
                <p className="text-gray-200 text-sm leading-relaxed">{p.problem}</p>
                <div className="flex items-center gap-3 flex-wrap">
                  <Badge
                    variant="outline"
                    className="text-[11px] bg-gray-800/60 text-gray-400 border-gray-700"
                  >
                    r/{p.subreddit}
                  </Badge>
                  <span className="text-xs text-gray-500 font-mono">↑ {p.upvotes.toLocaleString()}</span>
                  {p.source_url && (
                    <a
                      href={p.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-indigo-400 hover:text-indigo-300 transition-colors ml-auto"
                    >
                      Reddit →
                    </a>
                  )}
                </div>
              </div>
            ))
          )}
        </CardContent>
      </Card>

      {/* Ideas section */}
      <Card className="bg-gray-900 border-gray-800">
        <CardHeader>
          <CardTitle className="text-sm font-semibold text-gray-300 uppercase tracking-wider">
            Идеи из этой боли ({clusterIdeas.length})
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {clusterIdeas.length === 0 ? (
            <p className="text-gray-600 text-sm text-center py-4">Нет идей</p>
          ) : (
            clusterIdeas.map(idea => (
              <div
                key={idea.id}
                className="border border-gray-800 rounded-lg p-4 bg-gray-800/20 hover:bg-gray-800/40 transition-colors"
              >
                <div className="flex items-start gap-3">
                  <span
                    className={`shrink-0 inline-flex items-center justify-center w-10 h-8 rounded-md font-bold font-mono text-sm tabular-nums ${ideaScoreColor(idea.score)}`}
                  >
                    {idea.score}
                  </span>
                  <div className="flex-1 min-w-0 space-y-1">
                    <Link
                      to={`/ideas/${idea.id}`}
                      className="block text-sm font-medium text-gray-200 hover:text-indigo-400 transition-colors leading-snug"
                    >
                      {idea.title}
                    </Link>
                    {idea.pain && (
                      <p className="text-xs text-gray-500 line-clamp-2">{idea.pain}</p>
                    )}
                  </div>
                </div>
              </div>
            ))
          )}
        </CardContent>
      </Card>
    </div>
  )
}
