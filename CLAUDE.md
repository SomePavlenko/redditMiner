# Reddit Miner — контекст проекта

## Что это
Личный некоммерческий инструмент для анализа публичных обсуждений Reddit.
Выявляет частые проблемы пользователей, кластеризует боли, генерирует продуктовые идеи с оценками.

## Стек
- Python 3.12 — скрипты (стадии) и FastAPI
- SQLite (WAL mode) — данные в data/miner.db
- React + Vite + Tailwind + Recharts — фронтенд localhost:3000
- FastAPI — REST API localhost:8000
- Reddit публичный JSON API — без OAuth
- Claude Code — анализ через терминал (без API ключа)

## Пайплайн

```
S0 Разведка       → сабреддиты в БД
S1a Посты          → Reddit JSON → trimmer → raw_posts
S1b Комменты       → Reddit JSON → trimmer → raw_posts.comments_json
S2 Батчи           → data/batches/*.json (с _prompt внутри)
   [Claude Code]   → data/problems_raw.json
S3 Сохранение      → problems в БД (скрипт, не Claude)
S4 Кластеризация   → data/cluster_prompt.json
   [Claude Code]   → data/clusters_raw.json
S4 --save          → pain_clusters в БД (с pain_score)
S5 Идеи            → data/ideas_prompt.json
   [Claude Code]   → data/ideas_raw.json
S5 --save          → ideas в БД (со скорингом + дедуп)
S6 Перепарсинг     → Telegram напоминания
```

## Стадии

| Стадия | Файл | Запуск |
|---|---|---|
| S0 Разведка | `s0_scout_subreddits.py` | `--add jobs,resumes` или промпт для Claude Code |
| S1 Сбор | `s1_fetch_reddit.py` | `posts` / `comments` / без аргументов = оба |
| — Обрезка | `trimmer.py` | утилита, не запускается отдельно |
| S2 Батчи | `s2_prepare_batches.py` | готовит JSON с _prompt |
| S3 Боли → БД | `s3_save_problems.py` | читает problems_raw.json → INSERT |
| S4 Кластеры | `s4_cluster_problems.py` | без аргументов = промпт / `--save` = в БД |
| S5 Идеи | `s5_generate_ideas.py` | без аргументов = промпт / `--save` = скоринг + БД |
| S6 Перепарсинг | `s6_reparse_check.py` | Telegram напоминания |
| Тест | `test_flow.py` | мини-прогон |
| Пайплайн | `run_pipeline.py` | `--after-s2` / `--after-s4` |

## Промпты для Claude Code

| Файл | Стадия | Что делает |
|---|---|---|
| `data/find_subreddits_prompt.txt` | S0 | Поиск сабреддитов по теме |
| `data/batches/batch_NNN.json` → `_prompt` | S2 | Извлечение болей из постов |
| `data/cluster_prompt.json` → `_prompt` | S4 | Кластеризация + названия болей |
| `data/ideas_prompt.json` → `_prompt` | S5 | Генерация идей + оценки |

## Скоринг

### pain_score (боль кластера, считает скрипт):
```
pain_score = frequency×2 + subreddit_spread×3 + log(total_upvotes+1)
```

### idea score (финальный, считает скрипт):
```
score = demand×0.35 + breadth×0.25 + feasibility×0.20 + uniqueness×0.20
```
- demand: средний pain_score решаемых кластеров (из данных)
- breadth: сколько кластеров покрывает (из данных)
- feasibility: Claude оценивает (2 разработчика, MVP 2-4 недели)
- uniqueness: Claude оценивает (наличие аналогов)

## Конфиг
Все настройки в `config.json`. Описание: `docs/config_reference.md`

## Запуск

```bash
# Тест
python3 -m workers.test_flow

# Полный пайплайн (3 этапа с паузами на Claude Code)
python3 -m workers.run_pipeline
# → Claude Code анализирует батчи → сохраняет problems_raw.json
python3 -m workers.run_pipeline --after-s2
# → Claude Code кластеризует → сохраняет clusters_raw.json
python3 -m workers.run_pipeline --after-s4
# → Claude Code генерит идеи → сохраняет ideas_raw.json
python3 -m workers.s5_generate_ideas --save
```
