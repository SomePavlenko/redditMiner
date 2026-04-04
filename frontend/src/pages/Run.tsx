import { useState, useEffect, useRef, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { cn } from '@/lib/utils'

interface LogEntry {
  type: string
  stage?: string
  name?: string
  text?: string
  elapsed?: number
}

interface TopIdea {
  id: number
  title: string
  score: number
  pain: string
  competition_level: string
  monetization: string
  validation_step: string
}

interface TopCluster {
  id: number
  cluster_name: string
  pain_score: number
  frequency: number
  summary: string
}

interface RunResult {
  success: boolean
  topic: string
  failed_stage?: string
  stats?: { posts: number; problems: number; clusters: number; ideas: number }
  top_ideas?: TopIdea[]
  top_clusters?: TopCluster[]
}

interface Config {
  topic: string
  min_upvotes: number
  reddit_api_limit: number
  body_max_chars: number
  comment_max_chars: number
  comments_top_n: number
  posts_for_comments_n: number
  claude_batch_size: number
}

type Phase = 'setup' | 'running' | 'done'

const STAGE_ORDER = ['S0', 'S1', 'S2', 'S3', 'S4', 'S5']
const STAGE_NAMES: Record<string, string> = {
  S0: 'Разведка сабреддитов',
  S1: 'Парсинг Reddit',
  S2: 'Подготовка батчей',
  S3: 'Анализ болей',
  S4: 'Кластеризация',
  S5: 'Генерация идей',
}

const competitionLabel: Record<string, { text: string; class: string }> = {
  none:   { text: 'нет рынка',  class: 'bg-yellow-900/30 text-yellow-400 border-yellow-800' },
  low:    { text: 'слабая',     class: 'bg-yellow-900/20 text-yellow-300 border-yellow-800' },
  medium: { text: 'умеренная',  class: 'bg-green-900/30 text-green-400 border-green-800' },
  high:   { text: 'высокая',   class: 'bg-red-900/30 text-red-400 border-red-800' },
}

export default function Run() {
  const [phase, setPhase] = useState<Phase>('setup')
  const [config, setConfig] = useState<Config | null>(null)
  const [topicOverride, setTopicOverride] = useState('')
  const [params, setParams] = useState({
    min_upvotes: 50,
    reddit_api_limit: 55,
    posts_for_comments_n: 15,
    claude_batch_size: 20,
    body_max_chars: 300,
  })
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [activeStage, setActiveStage] = useState<string | null>(null)
  const [completedStages, setCompletedStages] = useState<Set<string>>(new Set())
  const [failedStage, setFailedStage] = useState<string | null>(null)
  const [result, setResult] = useState<RunResult | null>(null)
  const logsEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    fetch('/api/config').then(r => r.json()).then((c: Config) => {
      setConfig(c)
      setTopicOverride(c.topic)
      setParams({
        min_upvotes: c.min_upvotes ?? 50,
        reddit_api_limit: c.reddit_api_limit ?? 55,
        posts_for_comments_n: c.posts_for_comments_n ?? 15,
        claude_batch_size: c.claude_batch_size ?? 20,
        body_max_chars: c.body_max_chars ?? 300,
      })
    }).catch(() => {})
  }, [])

  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs])

  const startRun = useCallback(() => {
    setPhase('running')
    setLogs([])
    setActiveStage(null)
    setCompletedStages(new Set())
    setFailedStage(null)
    setResult(null)

    const qp = new URLSearchParams()
    if (topicOverride) qp.set('topic', topicOverride)
    qp.set('min_upvotes', String(params.min_upvotes))
    qp.set('reddit_api_limit', String(params.reddit_api_limit))
    qp.set('posts_for_comments_n', String(params.posts_for_comments_n))
    qp.set('claude_batch_size', String(params.claude_batch_size))
    qp.set('body_max_chars', String(params.body_max_chars))
    const evtSource = new EventSource(`/api/run/stream?${qp}`)

    evtSource.onmessage = (event) => {
      const data = JSON.parse(event.data)

      if (data.type === 'stage_start') {
        setActiveStage(data.stage)
        setLogs(prev => [...prev, { type: 'stage_start', stage: data.stage, name: data.name }])
      } else if (data.type === 'log') {
        setLogs(prev => [...prev, data])
      } else if (data.type === 'stage_done') {
        setCompletedStages(prev => new Set([...prev, data.stage]))
        setActiveStage(null)
        setLogs(prev => [...prev, { type: 'stage_done', stage: data.stage, elapsed: data.elapsed }])
      } else if (data.type === 'stage_error') {
        setFailedStage(data.stage)
        setActiveStage(null)
        setLogs(prev => [...prev, { type: 'stage_error', stage: data.stage, elapsed: data.elapsed }])
      } else if (data.type === 'done') {
        setResult(data as RunResult)
        setPhase('done')
        evtSource.close()
      }
    }

    evtSource.onerror = () => {
      evtSource.close()
      if (phase === 'running') {
        setPhase('done')
        setResult({ success: false, topic: topicOverride, failed_stage: 'connection' })
      }
    }
  }, [topicOverride, config, phase])

  // ── Setup phase ──

  if (phase === 'setup' && config) {
    return (
      <div className="max-w-2xl mx-auto space-y-6">
        <h1 className="text-2xl font-bold">Запуск анализа</h1>

        <Card className="bg-gray-900 border-gray-800">
          <CardHeader><CardTitle className="text-base text-white">Тема</CardTitle></CardHeader>
          <CardContent>
            <input
              value={topicOverride}
              onChange={e => setTopicOverride(e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-sm text-gray-100 focus:border-indigo-500 focus:outline-none"
              placeholder="Тема для анализа"
            />
          </CardContent>
        </Card>

        <Card className="bg-gray-900 border-gray-800">
          <CardHeader><CardTitle className="text-base text-white">Параметры</CardTitle></CardHeader>
          <CardContent>
            <div className="space-y-3">
              {([
                ['min_upvotes', 'Мин. апвоутов'],
                ['reddit_api_limit', 'Reddit лимит'],
                ['posts_for_comments_n', 'Комментов к постам'],
                ['claude_batch_size', 'Размер батча'],
                ['body_max_chars', 'Body лимит (символов)'],
              ] as const).map(([key, label]) => (
                <div key={key} className="flex items-center gap-4">
                  <span className="text-sm text-gray-400 w-48">{label}</span>
                  <input
                    type="number"
                    value={params[key]}
                    onChange={e => setParams(p => ({ ...p, [key]: Number(e.target.value) || 0 }))}
                    className="w-20 bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-center text-gray-100 focus:border-indigo-500 focus:outline-none"
                  />
                </div>
              ))}
            </div>
            <p className="text-xs text-gray-600 mt-3">Значения для этого прогона. Конфиг не меняется.</p>
          </CardContent>
        </Card>

        <Card className="bg-gray-900 border-gray-800">
          <CardHeader><CardTitle className="text-base text-white">Пайплайн</CardTitle></CardHeader>
          <CardContent className="space-y-2">
            {STAGE_ORDER.map(s => (
              <div key={s} className="flex items-center gap-3 text-sm">
                <span className="text-gray-600 font-mono w-6">{s}</span>
                <span className="text-gray-300">{STAGE_NAMES[s]}</span>
              </div>
            ))}
          </CardContent>
        </Card>

        <Button onClick={startRun} className="w-full bg-indigo-600 hover:bg-indigo-500 text-white" size="lg">
          Запустить анализ
        </Button>
      </div>
    )
  }

  // ── Running / Done phase ──

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">
          {phase === 'running' ? 'Анализ запущен...' : result?.success ? 'Анализ завершён' : 'Ошибка'}
        </h1>
        {phase === 'done' && (
          <Button variant="outline" onClick={() => setPhase('setup')} className="bg-gray-800 border-gray-700">
            Новый запуск
          </Button>
        )}
      </div>

      {/* Progress bar */}
      <div className="flex gap-1">
        {STAGE_ORDER.map(s => (
          <div key={s} className="flex-1 flex flex-col items-center gap-1">
            <div className={cn(
              'w-full h-2 rounded-full transition-colors',
              completedStages.has(s) ? 'bg-green-500' :
              activeStage === s ? 'bg-indigo-500 animate-pulse' :
              failedStage === s ? 'bg-red-500' :
              'bg-gray-800'
            )} />
            <span className="text-[10px] text-gray-500">{s}</span>
          </div>
        ))}
      </div>

      {/* Logs */}
      <Card className="bg-gray-950 border-gray-800">
        <CardContent className="p-0">
          <div className="h-80 overflow-y-auto font-mono text-xs p-4 space-y-0.5">
            {logs.map((log, i) => {
              if (log.type === 'stage_start') {
                return <div key={i} className="text-indigo-400 font-semibold mt-2">▶ {log.stage} {log.name}</div>
              }
              if (log.type === 'stage_done') {
                return <div key={i} className="text-green-400">✓ {log.stage} завершён ({log.elapsed}s)</div>
              }
              if (log.type === 'stage_error') {
                return <div key={i} className="text-red-400">✗ {log.stage} ошибка ({log.elapsed}s)</div>
              }
              return <div key={i} className="text-gray-400">{log.text}</div>
            })}
            <div ref={logsEndRef} />
          </div>
        </CardContent>
      </Card>

      {/* Results */}
      {phase === 'done' && result?.success && (
        <>
          <Separator className="bg-gray-800" />

          {/* Stats */}
          <div className="grid grid-cols-4 gap-3">
            {[
              { label: 'Постов', value: result.stats?.posts },
              { label: 'Болей', value: result.stats?.problems },
              { label: 'Кластеров', value: result.stats?.clusters },
              { label: 'Идей', value: result.stats?.ideas },
            ].map(s => (
              <Card key={s.label} className="bg-gray-900 border-gray-800">
                <CardContent className="p-4 text-center">
                  <div className="text-2xl font-bold text-white">{s.value ?? 0}</div>
                  <div className="text-xs text-gray-500 mt-1">{s.label}</div>
                </CardContent>
              </Card>
            ))}
          </div>

          {/* Top Ideas */}
          {result.top_ideas && result.top_ideas.length > 0 && (
            <Card className="bg-gray-900 border-gray-800">
              <CardHeader><CardTitle className="text-base">Топ идеи</CardTitle></CardHeader>
              <CardContent className="space-y-3">
                {result.top_ideas.map(idea => {
                  const comp = competitionLabel[idea.competition_level]
                  return (
                    <Link key={idea.id} to={`/ideas/${idea.id}`} className="block bg-gray-800/50 rounded-lg p-4 hover:bg-gray-800 transition-colors">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="flex items-center gap-2 mb-1">
                            <span className={cn(
                              'text-xs font-bold px-1.5 py-0.5 rounded',
                              idea.score >= 7 ? 'bg-green-600/20 text-green-400' : 'bg-yellow-600/20 text-yellow-400'
                            )}>{idea.score}</span>
                            <span className="font-medium text-white text-sm">{idea.title}</span>
                          </div>
                          {idea.pain && <p className="text-xs text-gray-400 mt-1">{idea.pain}</p>}
                          {idea.validation_step && (
                            <p className="text-xs text-green-400/70 mt-1">→ {idea.validation_step}</p>
                          )}
                        </div>
                        <div className="flex flex-col items-end gap-1 shrink-0">
                          {comp && <Badge variant="outline" className={cn('text-[10px]', comp.class)}>{comp.text}</Badge>}
                          {idea.monetization && <span className="text-[10px] text-gray-500 max-w-[150px] text-right truncate">{idea.monetization}</span>}
                        </div>
                      </div>
                    </Link>
                  )
                })}
              </CardContent>
            </Card>
          )}

          {/* Top Clusters */}
          {result.top_clusters && result.top_clusters.length > 0 && (
            <Card className="bg-gray-900 border-gray-800">
              <CardHeader><CardTitle className="text-base">Топ кластеры болей</CardTitle></CardHeader>
              <CardContent className="space-y-2">
                {result.top_clusters.map(c => (
                  <Link key={c.id} to={`/clusters/${c.id}`} className="block bg-gray-800/50 rounded-lg p-3 hover:bg-gray-800 transition-colors">
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium text-pink-300">{c.cluster_name}</span>
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-gray-500">×{c.frequency}</span>
                        <Badge variant="outline" className="text-[10px] bg-pink-900/20 text-pink-400 border-pink-800">
                          {c.pain_score.toFixed(1)}
                        </Badge>
                      </div>
                    </div>
                    <p className="text-xs text-gray-500 mt-1">{c.summary}</p>
                  </Link>
                ))}
              </CardContent>
            </Card>
          )}
        </>
      )}

      {phase === 'done' && !result?.success && (
        <Card className="bg-red-950/20 border-red-900/50">
          <CardContent className="p-6 text-center">
            <p className="text-red-400">Пайплайн остановился на стадии {result?.failed_stage}</p>
            <p className="text-sm text-gray-500 mt-2">Проверь логи выше для деталей</p>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
