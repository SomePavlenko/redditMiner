import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  BarChart, Bar, Cell,
} from 'recharts'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'

// ─── Types ────────────────────────────────────────────────────────────────────

interface Stats {
  total_ideas: number
  total_problems: number
  total_clusters: number
  total_subreddits: number
}

interface Sub {
  name: string
  weight: number
  total_ideas: number
  last_parsed_at: string
}

interface Idea {
  id: number
  title: string
  score: number
  revenue_model: string
  feasibility_score: number
  created_at: string
}

interface Cluster {
  id: number
  cluster_name: string
  pain_score: number
  frequency: number
  subreddit_spread: number
  summary?: string
}

// ─── Constants ────────────────────────────────────────────────────────────────

const BAR_COLORS = [
  '#818cf8', '#a78bfa', '#c084fc', '#e879f9', '#f472b6',
  '#fb7185', '#f87171', '#fb923c', '#fbbf24', '#a3e635',
]

const TOOLTIP_STYLE = {
  background: '#111827',
  border: '1px solid #1f2937',
  borderRadius: 8,
  fontSize: 12,
  color: '#e5e7eb',
}

const AXIS_TICK = { fill: '#6b7280', fontSize: 11 }

// ─── Sub-components ───────────────────────────────────────────────────────────

function StatCard({ label, value, accent }: { label: string; value: number | null; accent: string }) {
  return (
    <Card className="bg-gray-900 border-gray-800">
      <CardContent className="pt-5 pb-5">
        <p className="text-xs font-medium uppercase tracking-wider text-gray-500 mb-1">{label}</p>
        <p className={`text-4xl font-bold tabular-nums ${accent}`}>
          {value === null ? <span className="text-gray-700 text-2xl">—</span> : value.toLocaleString()}
        </p>
      </CardContent>
    </Card>
  )
}

function PainScoreBar({ score }: { score: number }) {
  // pain_score is expected 0–10
  const pct = Math.min(100, Math.max(0, (score / 10) * 100))
  const color =
    pct >= 70 ? '#f87171' :
    pct >= 40 ? '#fbbf24' :
    '#34d399'
  return (
    <div className="flex items-center gap-2 min-w-[120px]">
      <div className="flex-1 h-1.5 rounded-full bg-gray-800 overflow-hidden">
        <div
          className="h-full rounded-full transition-all"
          style={{ width: `${pct}%`, background: color }}
        />
      </div>
      <span className="text-xs font-mono tabular-nums text-gray-400 w-7 text-right">
        {score.toFixed(1)}
      </span>
    </div>
  )
}

function feasibilityLabel(score: number) {
  if (score >= 7) return { text: 'High', variant: 'secondary' as const }
  if (score >= 4) return { text: 'Mid', variant: 'outline' as const }
  return { text: 'Low', variant: 'destructive' as const }
}

// ─── Main Component ───────────────────────────────────────────────────────────

export default function Trends() {
  const [stats, setStats] = useState<Stats | null>(null)
  const [ideasByDay, setIdeasByDay] = useState<{ date: string; count: number }[]>([])
  const [topSubs, setTopSubs] = useState<Sub[]>([])
  const [topIdeas, setTopIdeas] = useState<Idea[]>([])
  const [topClusters, setTopClusters] = useState<Cluster[]>([])
  const [expandedCluster, setExpandedCluster] = useState<number | null>(null)

  useEffect(() => {
    // Stats summary
    fetch('/api/stats')
      .then(r => r.json())
      .then(setStats)
      .catch(() => {})

    // Ideas — derive "by day" chart + top-10 table
    fetch('/api/ideas?limit=1000')
      .then(r => r.json())
      .then((ideas: Idea[]) => {
        const byDay: Record<string, number> = {}
        ideas.forEach(i => {
          const d = i.created_at?.split('T')[0] ?? i.created_at?.split(' ')[0]
          if (d) byDay[d] = (byDay[d] || 0) + 1
        })
        const chartData = Object.entries(byDay)
          .map(([date, count]) => ({ date, count }))
          .sort((a, b) => a.date.localeCompare(b.date))
          .slice(-30)
        setIdeasByDay(chartData)
        setTopIdeas([...ideas].sort((a, b) => b.score - a.score).slice(0, 10))
      })
      .catch(() => {})

    // Subreddits
    fetch('/api/subreddits')
      .then(r => r.json())
      .then((subs: Sub[]) => setTopSubs(subs.slice(0, 10)))
      .catch(() => {})

    // Clusters
    fetch('/api/clusters?limit=10')
      .then(r => r.json())
      .then((clusters: Cluster[]) =>
        setTopClusters([...clusters].sort((a, b) => b.pain_score - a.pain_score).slice(0, 10))
      )
      .catch(() => {})
  }, [])

  return (
    <div className="space-y-8 pb-12">
      <h1 className="text-2xl font-bold tracking-tight">Analytics</h1>

      {/* ── 1. Stats row ─────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatCard label="Total ideas"      value={stats?.total_ideas      ?? null} accent="text-indigo-400" />
        <StatCard label="Total problems"   value={stats?.total_problems   ?? null} accent="text-violet-400" />
        <StatCard label="Pain clusters"    value={stats?.total_clusters   ?? null} accent="text-pink-400"   />
        <StatCard label="Subreddits"       value={stats?.total_subreddits ?? null} accent="text-amber-400"  />
      </div>

      {/* ── 2. Ideas per day ─────────────────────────────────────────────── */}
      <Card className="bg-gray-900 border-gray-800">
        <CardHeader>
          <CardTitle className="text-sm font-semibold text-gray-300 uppercase tracking-wider">
            Ideas per day — last 30 days
          </CardTitle>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={ideasByDay} margin={{ top: 4, right: 8, bottom: 0, left: -16 }}>
              <XAxis
                dataKey="date"
                tick={AXIS_TICK}
                tickFormatter={d => d.slice(5)}
                interval="preserveStartEnd"
              />
              <YAxis tick={AXIS_TICK} allowDecimals={false} />
              <Tooltip
                contentStyle={TOOLTIP_STYLE}
                labelStyle={{ color: '#9ca3af' }}
                itemStyle={{ color: '#818cf8' }}
              />
              <Line
                type="monotone"
                dataKey="count"
                stroke="#818cf8"
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4, fill: '#818cf8' }}
              />
            </LineChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      {/* ── 3. Top pain clusters ─────────────────────────────────────────── */}
      <Card className="bg-gray-900 border-gray-800">
        <CardHeader>
          <CardTitle className="text-sm font-semibold text-gray-300 uppercase tracking-wider">
            Top pain clusters
          </CardTitle>
        </CardHeader>
        <CardContent>
          {topClusters.length === 0 ? (
            <p className="text-gray-600 text-sm text-center py-8">No cluster data yet</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="text-gray-500 text-xs uppercase tracking-wider border-b border-gray-800">
                    <th className="pb-3 pr-4 font-medium">#</th>
                    <th className="pb-3 pr-4 font-medium">Cluster</th>
                    <th className="pb-3 pr-4 font-medium w-44">Pain score</th>
                    <th className="pb-3 pr-4 font-medium text-right">Frequency</th>
                    <th className="pb-3 font-medium text-right">Subreddits</th>
                  </tr>
                </thead>
                <tbody>
                  {topClusters.map((c, i) => (
                    <>
                      <tr
                        key={c.id ?? c.cluster_name}
                        className="border-b border-gray-800/50 hover:bg-gray-800/30 transition-colors"
                      >
                        <td className="py-3 pr-4 text-gray-600 font-mono text-xs">{i + 1}</td>
                        <td className="py-3 pr-4 font-medium text-gray-200 max-w-[260px]">
                          <span
                            className="line-clamp-1 cursor-pointer hover:text-indigo-400 transition-colors"
                            onClick={() => setExpandedCluster(expandedCluster === c.id ? null : c.id)}
                          >
                            {c.cluster_name}
                          </span>
                        </td>
                        <td className="py-3 pr-4">
                          <PainScoreBar score={c.pain_score} />
                        </td>
                        <td className="py-3 pr-4 text-right font-mono text-gray-400">
                          {c.frequency?.toLocaleString() ?? '—'}
                        </td>
                        <td className="py-3 text-right">
                          <Badge variant="outline" className="font-mono text-xs border-gray-700 text-gray-400">
                            {c.subreddit_spread ?? '—'}
                          </Badge>
                        </td>
                      </tr>
                      {expandedCluster === c.id && (
                        <tr key={`${c.id}-expanded`} className="border-b border-gray-800/50">
                          <td colSpan={5} className="px-4 pb-4 pt-2 bg-gray-800/20">
                            {c.summary ? (
                              <p className="text-sm text-gray-400 mb-3">{c.summary}</p>
                            ) : (
                              <p className="text-sm text-gray-600 italic mb-3">Нет описания</p>
                            )}
                            <Link
                              to={`/clusters/${c.id}`}
                              className="inline-flex items-center text-sm text-indigo-400 hover:text-indigo-300 transition-colors"
                            >
                              Подробнее →
                            </Link>
                          </td>
                        </tr>
                      )}
                    </>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* ── 4. Top subreddits by weight ──────────────────────────────────── */}
      <Card className="bg-gray-900 border-gray-800">
        <CardHeader>
          <CardTitle className="text-sm font-semibold text-gray-300 uppercase tracking-wider">
            Top subreddits by weight
          </CardTitle>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart
              data={topSubs}
              layout="vertical"
              margin={{ top: 0, right: 8, bottom: 0, left: 0 }}
            >
              <XAxis type="number" tick={AXIS_TICK} />
              <YAxis
                type="category"
                dataKey="name"
                tick={AXIS_TICK}
                width={110}
                tickFormatter={n => `r/${n}`}
              />
              <Tooltip
                contentStyle={TOOLTIP_STYLE}
                labelStyle={{ color: '#9ca3af' }}
                formatter={(v) => [String(v), 'weight']}
              />
              <Bar dataKey="weight" radius={[0, 4, 4, 0]}>
                {topSubs.map((_, i) => (
                  <Cell key={i} fill={BAR_COLORS[i % BAR_COLORS.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      {/* ── 5. Top ideas ─────────────────────────────────────────────────── */}
      <Card className="bg-gray-900 border-gray-800">
        <CardHeader>
          <CardTitle className="text-sm font-semibold text-gray-300 uppercase tracking-wider">
            Top ideas by score
          </CardTitle>
        </CardHeader>
        <CardContent>
          {topIdeas.length === 0 ? (
            <p className="text-gray-600 text-sm text-center py-8">No ideas yet</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="text-gray-500 text-xs uppercase tracking-wider border-b border-gray-800">
                    <th className="pb-3 pr-4 font-medium w-14">Score</th>
                    <th className="pb-3 pr-4 font-medium">Title</th>
                    <th className="pb-3 pr-4 font-medium hidden md:table-cell">Revenue model</th>
                    <th className="pb-3 font-medium text-right">Feasibility</th>
                  </tr>
                </thead>
                <tbody>
                  {topIdeas.map(idea => {
                    const feas = feasibilityLabel(idea.feasibility_score ?? 0)
                    return (
                      <tr
                        key={idea.id}
                        className="border-b border-gray-800/50 hover:bg-gray-800/30 transition-colors"
                      >
                        <td className="py-3 pr-4">
                          <span className="inline-flex items-center justify-center w-9 h-7 rounded-md bg-indigo-500/15 text-indigo-400 font-bold font-mono text-sm tabular-nums">
                            {idea.score}
                          </span>
                        </td>
                        <td className="py-3 pr-4 text-gray-200 max-w-[320px]">
                          <Link
                            to={`/ideas/${idea.id}`}
                            className="line-clamp-2 leading-snug hover:text-indigo-400 transition-colors"
                          >
                            {idea.title}
                          </Link>
                        </td>
                        <td className="py-3 pr-4 hidden md:table-cell">
                          {idea.revenue_model ? (
                            <Badge variant="secondary" className="text-xs font-normal max-w-[200px] truncate">
                              {idea.revenue_model}
                            </Badge>
                          ) : (
                            <span className="text-gray-700">—</span>
                          )}
                        </td>
                        <td className="py-3 text-right">
                          <Badge variant={feas.variant} className="text-xs">
                            {feas.text}
                          </Badge>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
