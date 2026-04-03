import { useState, useEffect } from 'react'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, BarChart, Bar, Cell } from 'recharts'

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
  created_at: string
}

const COLORS = ['#818cf8', '#a78bfa', '#c084fc', '#e879f9', '#f472b6', '#fb7185', '#f87171', '#fb923c', '#fbbf24', '#a3e635']

export default function Trends() {
  const [ideasByDay, setIdeasByDay] = useState<{ date: string; count: number }[]>([])
  const [topSubs, setTopSubs] = useState<Sub[]>([])
  const [topIdeas, setTopIdeas] = useState<Idea[]>([])

  useEffect(() => {
    fetch('/api/ideas?limit=1000')
      .then(r => r.json())
      .then((ideas: Idea[]) => {
        const byDay: Record<string, number> = {}
        ideas.forEach(i => {
          const d = i.created_at?.split('T')[0] || i.created_at?.split(' ')[0]
          if (d) byDay[d] = (byDay[d] || 0) + 1
        })
        const sorted = Object.entries(byDay)
          .map(([date, count]) => ({ date, count }))
          .sort((a, b) => a.date.localeCompare(b.date))
          .slice(-30)
        setIdeasByDay(sorted)
        setTopIdeas(ideas.sort((a, b) => b.score - a.score).slice(0, 5))
      })
      .catch(() => {})

    fetch('/api/subreddits')
      .then(r => r.json())
      .then((subs: Sub[]) => setTopSubs(subs.slice(0, 10)))
      .catch(() => {})
  }, [])

  return (
    <div className="space-y-8">
      <h1 className="text-2xl font-bold">Тренды</h1>

      <div className="bg-gray-900 rounded-xl p-6">
        <h2 className="text-lg font-semibold mb-4">Идеи по дням (30 дней)</h2>
        <ResponsiveContainer width="100%" height={250}>
          <LineChart data={ideasByDay}>
            <XAxis dataKey="date" tick={{ fill: '#9ca3af', fontSize: 12 }} />
            <YAxis tick={{ fill: '#9ca3af', fontSize: 12 }} />
            <Tooltip contentStyle={{ background: '#1f2937', border: 'none', borderRadius: 8 }} />
            <Line type="monotone" dataKey="count" stroke="#818cf8" strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="bg-gray-900 rounded-xl p-6">
        <h2 className="text-lg font-semibold mb-4">Топ-10 сабреддитов по весу</h2>
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={topSubs} layout="vertical">
            <XAxis type="number" tick={{ fill: '#9ca3af', fontSize: 12 }} />
            <YAxis type="category" dataKey="name" tick={{ fill: '#9ca3af', fontSize: 12 }} width={120} />
            <Tooltip contentStyle={{ background: '#1f2937', border: 'none', borderRadius: 8 }} />
            <Bar dataKey="weight" radius={[0, 4, 4, 0]}>
              {topSubs.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="bg-gray-900 rounded-xl p-6">
        <h2 className="text-lg font-semibold mb-4">Топ-5 идей всех времён</h2>
        <table className="w-full text-left">
          <thead>
            <tr className="text-gray-400 text-sm border-b border-gray-800">
              <th className="pb-2">Score</th>
              <th className="pb-2">Название</th>
              <th className="pb-2">Дата</th>
            </tr>
          </thead>
          <tbody>
            {topIdeas.map(idea => (
              <tr key={idea.id} className="border-b border-gray-800/50">
                <td className="py-2 font-mono text-indigo-400">{idea.score}</td>
                <td className="py-2">{idea.title}</td>
                <td className="py-2 text-gray-500 text-sm">{idea.created_at?.split('T')[0] || idea.created_at?.split(' ')[0]}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
