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
python3 -m workers.run_all
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

## Запуск воркеров

### Вся цепочка сразу (cold start)
```bash
python3 -m workers.run_all
```

### По отдельности
```bash
python3 -m workers.w0_topic --force   # найти сабреддиты для темы
python3 -m workers.w1_parser           # спарсить посты из Reddit (публичный JSON)
python3 -m workers.w2_analyzer         # подготовить батчи для анализа → data/batches/
python3 -m workers.w3_digest           # подготовить контекст для идей → data/digest_context.json
python3 -m workers.w4_reparse          # напомнить о старых сабреддитах
```

### Анализ через Claude Code (после W2/W3)
```bash
claude
> "Прочитай data/batches/, извлеки боли, запиши в БД таблица problems.
   Пометь посты processed=1. Потом прочитай data/digest_context.json,
   сгенерируй топ идеи и запиши в БД таблица ideas."
```

### Через API (из фронта или curl)
```bash
curl -X POST http://localhost:8000/api/workers/run/all
curl -X POST http://localhost:8000/api/workers/run/w1
```

---

## Автоматический запуск (cron)

### Вариант 1: через setup.sh
```bash
./setup.sh
```
Добавит cron задачи автоматически.

### Вариант 2: вручную
```bash
crontab -e
```
Добавить:
```
0 2 * * * cd /Users/alex/Documents/petProj/redditMiner && python3 -m workers.w1_parser >> logs/cron.log 2>&1
0 3 * * * cd /Users/alex/Documents/petProj/redditMiner && python3 -m workers.w2_analyzer >> logs/cron.log 2>&1
0 4 * * * cd /Users/alex/Documents/petProj/redditMiner && python3 -m workers.w3_digest >> logs/cron.log 2>&1
0 5 * * * cd /Users/alex/Documents/petProj/redditMiner && python3 -m workers.w4_reparse >> logs/cron.log 2>&1
```

Проверить что задачи добавлены: `crontab -l`

**Важно:** cron на macOS работает только когда мак не спит.

---

## Как работает система

```
Ночь 02:00  →  W1 парсит Reddit через публичный JSON (автоматически по cron)
      03:00  →  W2 готовит батчи из новых постов (автоматически по cron)
      04:00  →  W3 готовит контекст для дайджеста (автоматически по cron)
Утро        →  Открываешь Claude Code, запускаешь анализ батчей + генерацию идей
              →  Смотришь результаты на localhost:3000
```

---

## Смена темы исследования

Поменяй `topic` в `config.json`:
```json
{
  "topic": "remote work tools"
}
```
Запусти W0 чтобы найти новые сабреддиты:
```bash
python3 -m workers.w0_topic --force
```
Или поменяй через API — W0 запустится автоматически:
```bash
curl -X POST http://localhost:8000/api/config -H "Content-Type: application/json" -d '{"topic": "remote work tools"}'
```

---

## Структура проекта

```
config.json       ← настройки (тема, лимиты, расписание)
.env              ← секреты (API ключи) — не коммитится
data/miner.db     ← SQLite база со всеми данными
logs/             ← логи воркеров по дням
.topic_hash       ← хеш текущей темы для отслеживания изменений

workers/
  w0_topic.py     ← поиск сабреддитов по теме
  w1_parser.py    ← парсинг Reddit
  w2_analyzer.py  ← извлечение болей (Claude Haiku)
  w3_digest.py    ← генерация идей (Claude Sonnet) + Telegram
  w4_reparse.py   ← напоминания о перепарсинге
  run_all.py      ← запуск всей цепочки

api/main.py       ← FastAPI REST API
frontend/         ← React + Vite + Tailwind дашборд
```

---

## Полезные команды

```bash
# Посмотреть статистику
curl http://localhost:8000/api/stats

# Посмотреть идеи
curl http://localhost:8000/api/ideas

# Посмотреть сабреддиты
curl http://localhost:8000/api/subreddits

# Открыть БД напрямую
sqlite3 data/miner.db "SELECT title, score FROM ideas ORDER BY score DESC LIMIT 10;"

# Посмотреть логи
cat logs/w1_$(date +%Y%m%d).log
```
