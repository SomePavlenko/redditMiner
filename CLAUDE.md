# Reddit Miner — контекст проекта

## Что это
Личный некоммерческий инструмент для анализа публичных обсуждений Reddit.
Выявляет частые проблемы пользователей и группирует их по темам.

## Стек
- Python 3.11+ — все воркеры и FastAPI
- SQLite (WAL mode) — основная БД, файл data/miner.db
- React + Vite + Tailwind + Recharts — фронтенд на localhost:3000
- FastAPI — REST API на localhost:8000
- Reddit публичный JSON API — без OAuth, без токенов
- Claude Code — анализ данных вручную через терминал (без API ключа)

## Воркеры и порядок запуска
1. W0 — topic agent (разово при смене topic в config.json)
2. W1 — parser: парсит Reddit через публичный JSON
3. W2 — analyzer: готовит батчи для анализа через Claude Code
4. W3 — digest: готовит контекст для генерации идей через Claude Code
5. W4 — reparse suggestions (напоминания в Telegram)

Для первого запуска: python3 -m workers.run_all

## Режим запуска (локальный, без API)

### Режим 1 — Парсинг (автономный, без Claude)
```bash
python3 -m workers.w1_parser   # парсит Reddit через публичный JSON
```
Reddit JSON API: публичный, без токенов, лимит ~60 req/min по IP.
URL формат: https://www.reddit.com/r/{sub}/top.json?t=week&limit=100

### Режим 2 — Анализ (через Claude Code в терминале)
Подготовка данных:
```bash
python3 -m workers.w2_analyzer  # создаёт data/batches/*.json
python3 -m workers.w3_digest    # создаёт data/digest_context.json
```

Запуск анализа — открываешь Claude Code:
```bash
claude
```

Промпты для Claude Code:

**Извлечение болей из батчей:**
> Прочитай все файлы в data/batches/. Для каждого поста найди конкретные
> боли пользователей — что не работает, что раздражает, что хотят улучшить.
> Запиши результаты в БД data/miner.db таблица problems.
> Потом пометь посты как processed=1 в таблице raw_posts.

**Генерация дайджеста:**
> Прочитай data/digest_context.json. Найди топ бизнес-идеи которые решают
> эти боли. Для каждой идеи: название, описание, пример продукта, оценки
> (рынок/сложность/уникальность 1-10). Запиши в data/miner.db таблица ideas.

### Режим 3 — Автономный (с API ключом, опционально)
Если хочешь запускать без себя ночью — добавь ANTHROPIC_API_KEY в .env
и верни оригинальную логику вызовов API в w2/w3.

## Важные соглашения
- Все параметры только из config.json и .env, никаких хардкодов
- Каждый воркер логирует в logs/{worker}_{date}.log
- SQLite WAL mode включён при инициализации БД
- W0 определяет смену topic через MD5 hash в файле .topic_hash
- Reddit JSON: sleep 1.1s между запросами (лимит ~55 req/min)

## Статус разработки
- [x] Структура папок и БД
- [x] W0 topic agent
- [x] W1 parser (публичный JSON, без OAuth)
- [x] W2 analyzer (подготовка батчей для Claude Code)
- [x] W3 digest (подготовка контекста для Claude Code)
- [x] W4 reparse
- [x] FastAPI
- [x] React frontend
- [x] setup.sh + cron
