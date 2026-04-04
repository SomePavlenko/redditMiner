# Reddit Miner

> Личный некоммерческий проект для образовательных и исследовательских целей.

Автономная система анализа публичных обсуждений Reddit — выявляет частые проблемы пользователей и группирует их по темам.
Работает ночью по cron, результаты — на дашборде и в Telegram.

## Быстрый старт

```bash
# 1. Установить зависимости
pip install anthropic httpx fastapi uvicorn python-dotenv python-telegram-bot aiofiles
cd frontend && npm install && cd ..

# 2. Скопировать и заполнить .env
cp .env.example .env
# заполнить ANTHROPIC_API_KEY, REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET

# 3. Запустить API (терминал 1)
python3 -m uvicorn api.main:app --reload --port 8000

# 4. Запустить фронт (терминал 2)
cd frontend && npm run dev

# 5. Первый запуск цепочки (терминал 3)
python3 -m workers.run_pipeline
```

Фронт: http://localhost:3000
API docs: http://localhost:8000/docs

---

## Reddit API — настройка не нужна

Парсинг работает через **публичный Reddit JSON** — без OAuth, без токенов, без регистрации приложения.
URL формат: `https://www.reddit.com/r/{sub}/top.json?t=week&limit=100`

Лимит: ~60 запросов в минуту по IP. В config.json стоит `reddit_api_limit: 55` с запасом.

> Заявка на Reddit OAuth API была подана на случай если понадобится в будущем.
> Форма: https://support.reddithelp.com/hc/en-us/requests/new?ticket_form_id=14868593862164

---

## Анализ данных — через Claude Code (бесплатно)

Вместо Anthropic API ($) анализ запускается через **Claude Code в терминале** — используется подписка claude.ai.

Стоимость: **$0** (за счёт подписки Claude Pro/Max)

---

## Подключение Telegram бота (опционально)

Без Telegram всё работает — идеи копятся в БД и видны на фронте.
Telegram просто дублирует дайджест в чат.

1. Открой Telegram, найди **@BotFather**
2. Напиши `/newbot`
3. Придумай имя и username → получишь **токен** вида `123456789:ABCdefGHI...`
4. Найди своего нового бота в поиске Telegram и напиши ему любое сообщение
5. Открой в браузере:
   ```
   https://api.telegram.org/bot<ТВОЙ_ТОКЕН>/getUpdates
   ```
6. В ответе найди `"chat":{"id": 123456789}` — это твой **chat_id**
7. Вставь в `.env`:
   ```
   TELEGRAM_BOT_TOKEN=123456789:ABCdefGHI...
   TELEGRAM_CHAT_ID=123456789
   ```

---

## Запуск

### Полный автоматический пайплайн
```bash
# 1. Добавить сабреддиты (один раз)
python3 -m workers.s0_scout_subreddits --add jobs,resumes,careerguidance

# 2. Запустить всю цепочку (S0→S1→S2→S3→S4→S5)
python3 -m workers.run_pipeline
```

### По отдельности
```bash
python3 -m workers.s0_scout_subreddits --add jobs,resumes   # добавить сабреддиты
python3 -m workers.s1_fetch_reddit posts                     # парсить посты
python3 -m workers.s1_fetch_reddit comments                  # загрузить комменты к топ постам
python3 -m workers.s2_prepare_batches                        # подготовить батчи
python3 -m workers.s3_save_problems                          # анализ болей (Claude Haiku)
python3 -m workers.s4_cluster_problems                       # кластеризация (Claude Haiku)
python3 -m workers.s5_generate_ideas                         # генерация идей (Claude Sonnet)
```

### Тестовый прогон (для отладки)
```bash
python3 -m workers.test_flow
```

### Через API
```bash
curl -X POST http://localhost:8000/api/workers/run/pipeline
curl -X POST http://localhost:8000/api/workers/run/s1
```

---

## Автоматический запуск (cron)

```bash
crontab -e
```
Добавить:
```
0 2 * * * cd /Users/alex/Documents/petProj/redditMiner && python3 -m workers.run_pipeline >> logs/cron.log 2>&1
```

Один cron job запускает весь пайплайн (S0→S5) автоматически.

**Важно:** cron на macOS работает только когда мак не спит.

---

## Как работает система

```
Ночь 02:00  →  run_pipeline запускает:
                S0: проверяет сабреддиты
                S1: парсит Reddit (публичный JSON, без ключей)
                S2: режет данные через trimmer, формирует батчи
                S3: отправляет батчи в Claude Haiku → боли в БД
                S4: кластеризует боли через Claude Haiku → pain_clusters с pain_score
                S5: генерит идеи через Claude Sonnet → скоринг + дедуп → ideas в БД
Утро        →  Смотришь результаты на localhost:3000 или через API
```

---

## Смена темы

Поменяй `topic` в `config.json`, добавь сабреддиты:
```bash
python3 -m workers.s0_scout_subreddits --add newsubreddit1,newsubreddit2
```

---

## Структура проекта

```
config.json                  ← настройки (описание: docs/config_reference.md)
.env                         ← секреты (ANTHROPIC_API_KEY) — не коммитится
data/miner.db                ← SQLite база
logs/                        ← логи по дням

workers/
  s0_scout_subreddits.py     ← S0: разведка сабреддитов
  s1_fetch_reddit.py         ← S1: парсинг Reddit (посты + комменты)
  trimmer.py                 ← обрезка данных Reddit (97 полей → 7)
  s2_prepare_batches.py      ← S2: формирование батчей
  s3_save_problems.py        ← S3: анализ болей через Claude Haiku
  s4_cluster_problems.py     ← S4: кластеризация через Claude Haiku
  s5_generate_ideas.py       ← S5: идеи через Claude Sonnet + скоринг
  s6_reparse_check.py        ← S6: напоминания о перепарсинге (Telegram)
  run_pipeline.py            ← полный пайплайн S0→S5
  test_flow.py               ← тестовый мини-прогон

api/main.py                  ← FastAPI REST API
frontend/                    ← React + Vite + Tailwind дашборд
```

---

## Полезные команды

```bash
# Статистика
curl http://localhost:8000/api/stats

# Идеи
curl http://localhost:8000/api/ideas

# Кластеры болей
curl http://localhost:8000/api/clusters

# Боли
curl http://localhost:8000/api/problems

# БД напрямую
sqlite3 data/miner.db "SELECT title, score FROM ideas WHERE is_duplicate=0 ORDER BY score DESC LIMIT 10;"
sqlite3 data/miner.db "SELECT cluster_name, pain_score FROM pain_clusters ORDER BY pain_score DESC;"

# Логи
cat logs/s1_$(date +%Y%m%d).log
```
