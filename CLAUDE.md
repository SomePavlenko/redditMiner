# Reddit Miner — контекст проекта

## Что это
Личный некоммерческий инструмент для анализа публичных обсуждений Reddit.
Выявляет частые проблемы пользователей и группирует их по темам.

## Стек
- Python 3.12 — скрипты (стадии) и FastAPI
- SQLite (WAL mode) — основная БД, файл data/miner.db
- React + Vite + Tailwind + Recharts — фронтенд на localhost:3000
- FastAPI — REST API на localhost:8000
- Reddit публичный JSON API — без OAuth, без токенов
- Claude Code — анализ данных через терминал (без API ключа)

## Стадии пайплайна

| Стадия | Файл | Что делает |
|---|---|---|
| S0 Разведка | `s0_scout_subreddits.py` | Находит сабреддиты по теме (через Claude Code или `--add`) |
| S1 Сбор | `s1_fetch_reddit.py` | Парсит Reddit: посты (S1a) + комменты к топ постам (S1b) |
| — | `trimmer.py` | Обрезает данные Reddit до нужных полей (не стадия, утилита) |
| S2 Батчи | `s2_prepare_batches.py` | Формирует JSON-батчи с промптом для Claude Code |
| S3 Дайджест | `s3_prepare_digest.py` | Собирает контекст для генерации идей |
| S4 Перепарсинг | `s4_reparse_check.py` | Напоминает о старых сабреддитах (Telegram) |
| Тест | `test_flow.py` | Мини-прогон для отладки (1 сабреддит, 5 постов) |
| Пайплайн | `run_pipeline.py` | Полный прогон S0→S1→S2→S3 |

## Где лежат промпты для Claude Code

| Файл | Когда создаётся | Что внутри |
|---|---|---|
| `data/find_subreddits_prompt.txt` | S0 (если нет сабреддитов) | Промпт для поиска сабреддитов по теме |
| `data/batches/batch_NNN.json` → поле `_prompt` | S2 | Промпт для извлечения болей из постов |
| `data/digest_context.json` | S3 | Контекст для генерации бизнес-идей |

## Флоу данных

```
S0: тема из config.json → Claude Code находит сабреддиты → subreddits в БД
S1a: Reddit JSON → trimmer.trim_posts() → raw_posts (без комментов)
S1b: Reddit JSON → trimmer.trim_comments() → raw_posts.comments_json
S2: raw_posts → обрезка → data/batches/*.json (с промптом)
Claude Code: читает батчи → пишет в problems + ставит processed=1
S3: problems → data/digest_context.json
Claude Code: читает контекст → пишет в ideas
```

## Запуск

```bash
# Тестовый (отладка)
python3 -m workers.test_flow

# По стадиям
python3 -m workers.s0_scout_subreddits --add jobs,resumes,careerguidance
python3 -m workers.s1_fetch_reddit posts
python3 -m workers.s1_fetch_reddit comments
python3 -m workers.s2_prepare_batches
python3 -m workers.s3_prepare_digest

# Полный пайплайн
python3 -m workers.run_pipeline
```

## Конфиг
Все настройки в `config.json`. Описание полей: `docs/config_reference.md`

## Важные соглашения
- Все параметры только из config.json и .env, никаких хардкодов
- Скрипты (не Claude) режут данные через trimmer.py
- Claude получает только чистые обрезанные данные
- Каждый агент имеет свой промпт, контекст между запусками не сохраняется
- Reddit JSON: sleep 1.1s между запросами (лимит ~55 req/min)
- SQLite WAL mode, логи в logs/{stage}_{date}.log
