import { useMemo } from 'react'

interface Idea {
  id: number
  title: string
  description: string
  product_example: string
  score: number
  market_score: number
  difficulty_score: number
  uniqueness_score: number
  subreddits: string
  source_urls: string
  is_favourite: number
}

interface Props {
  idea: Idea
  onToggleFav: (id: number) => void
}

function scoreBadge(score: number) {
  if (score >= 8) return 'bg-green-600'
  if (score >= 6) return 'bg-yellow-600'
  return 'bg-gray-600'
}

export default function IdeaCard({ idea, onToggleFav }: Props) {
  const subs = useMemo(() => {
    try { return JSON.parse(idea.subreddits) as string[] } catch { return [] }
  }, [idea.subreddits])

  return (
    <div id={`idea-${idea.id}`} className="bg-gray-900 rounded-xl p-5 border border-gray-800 hover:border-gray-700 transition-colors">
      <div className="flex items-start justify-between gap-3 mb-2">
        <div className="flex items-center gap-2">
          <span className={`${scoreBadge(idea.score)} px-2 py-0.5 rounded text-xs font-bold`}>
            {idea.score}/10
          </span>
          <h3 className="font-semibold text-white">{idea.title}</h3>
        </div>
        <button onClick={() => onToggleFav(idea.id)}
          className={`text-xl shrink-0 ${idea.is_favourite ? 'text-yellow-400' : 'text-gray-600 hover:text-yellow-400'}`}>
          ★
        </button>
      </div>
      <p className="text-gray-300 text-sm mb-2">{idea.description}</p>
      <p className="text-gray-500 text-sm italic mb-3">→ {idea.product_example}</p>
      <div className="flex items-center gap-4 text-xs text-gray-400 mb-2">
        <span>Рынок <b className="text-gray-300">{idea.market_score}</b>/10</span>
        <span>Сложность <b className="text-gray-300">{idea.difficulty_score}</b>/10</span>
        <span>Уникальность <b className="text-gray-300">{idea.uniqueness_score}</b>/10</span>
      </div>
      {subs.length > 0 && (
        <div className="flex gap-1.5 flex-wrap">
          {subs.map(s => (
            <span key={s} className="bg-gray-800 text-gray-400 px-2 py-0.5 rounded text-xs">r/{s}</span>
          ))}
        </div>
      )}
    </div>
  )
}
