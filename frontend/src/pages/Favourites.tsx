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

export default function Favourites() {
  const [ideas, setIdeas] = useState<Idea[]>([])

  const fetchIdeas = useCallback(() => {
    fetch('/api/ideas?favourite=1')
      .then(r => r.json())
      .then(setIdeas)
      .catch(() => {})
  }, [])

  useEffect(() => { fetchIdeas() }, [fetchIdeas])

  const toggleFav = async (id: number) => {
    await fetch(`/api/ideas/${id}/favourite`, { method: 'POST' })
    fetchIdeas()
  }

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Избранные идеи</h1>
      {ideas.length === 0 ? (
        <p className="text-gray-500 text-center py-12">
          Нет избранных. Нажми ★ на карточке идеи чтобы добавить.
        </p>
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
