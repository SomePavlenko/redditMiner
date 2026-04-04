import { useState, useEffect, useCallback } from 'react'
import IdeaCard from '../components/IdeaCard'
import BubbleChart from '../components/BubbleChart'

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

interface Config {
  topic: string
}

export default function Daily() {
  const [ideas, setIdeas] = useState<Idea[]>([])
  const [config, setConfig] = useState<Config>({ topic: '' })
  const [date, setDate] = useState(() => new Date().toISOString().split('T')[0])
  const [view, setView] = useState<'bubbles' | 'list'>('list')

  const fetchIdeas = useCallback(() => {
    fetch(`/api/ideas?date=${date}&limit=100`)
      .then(r => r.json())
      .then(data => setIdeas(data.items || data || []))
      .catch(() => {})
  }, [date])

  useEffect(() => {
    fetch('/api/config').then(r => r.json()).then(setConfig).catch(() => {})
  }, [])

  useEffect(() => { fetchIdeas() }, [fetchIdeas])

  const shiftDate = (days: number) => {
    const d = new Date(date)
    d.setDate(d.getDate() + days)
    setDate(d.toISOString().split('T')[0])
  }

  const toggleFav = async (id: number) => {
    await fetch(`/api/ideas/${id}/favourite`, { method: 'POST' })
    fetchIdeas()
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">Reddit Miner — {config.topic}</h1>
        <div className="flex items-center gap-3">
          <button onClick={() => shiftDate(-1)} className="px-3 py-1 bg-gray-800 rounded hover:bg-gray-700">←</button>
          <span className="font-mono text-sm">{date}</span>
          <button onClick={() => shiftDate(1)} className="px-3 py-1 bg-gray-800 rounded hover:bg-gray-700">→</button>
        </div>
      </div>

      <div className="flex items-center gap-4 mb-6">
        <div className="flex gap-1 bg-gray-900 rounded-lg p-1">
          <button
            onClick={() => setView('bubbles')}
            className={`px-3 py-1 rounded text-sm ${view === 'bubbles' ? 'bg-gray-700 text-white' : 'text-gray-400'}`}
          >Граф</button>
          <button
            onClick={() => setView('list')}
            className={`px-3 py-1 rounded text-sm ${view === 'list' ? 'bg-gray-700 text-white' : 'text-gray-400'}`}
          >Список</button>
        </div>
      </div>

      {ideas.length === 0 ? (
        <p className="text-gray-500 text-center py-12">Нет идей за {date}</p>
      ) : view === 'bubbles' ? (
        <BubbleChart ideas={ideas} onSelect={() => {}} />
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {ideas.map(idea => (
            <IdeaCard key={idea.id} idea={idea} onToggleFav={toggleFav} />
          ))}
        </div>
      )}
    </div>
  )
}
