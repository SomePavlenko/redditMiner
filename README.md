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

## Получение Reddit API ключей (бесплатно)

С ноября 2025 Reddit требует **предварительное одобрение** перед созданием API приложения.

### Шаг 1: Подать заявку на API доступ

1. Открой форму (через VPN если из России):
   https://support.reddithelp.com/hc/en-us/requests/new?ticket_form_id=14868593862164
2. Заполни:
   - **What do you need assistance with?** → `API Access Request`
   - **Your email address** → твой email
   - **Which role?** → `Individual Developer` или `Researcher`
   - **Описание** (если есть поле):
     ```
     I'm building a personal, non-commercial script that reads public posts
     and top comments from subreddits related to job search topics.
     The script runs once daily and analyzes common user pain points
     for personal research purposes.
     Expected volume: under 100 API requests per day.
     I will only access publicly available data (posts, comments, subreddit listings).
     No user data collection, no commercial use, no redistribution of Reddit content.
     I have read and will comply with the Responsible Builder Policy.
     ```
3. Нажми **Submit** и жди ответ (обычно до 7 дней)

### Шаг 2: Создать приложение (после одобрения)

1. Иди на https://www.reddit.com/prefs/apps (через VPN)
2. Внизу нажми **"create another app..."**
3. Заполни:
   - **name:** любое (например `reddie-miner`)
   - **type:** `script`
   - **description:** `mining reddit posts`
   - **redirect uri:** `http://localhost:8080` (обязательное поле, но не используется)
   - **about url:** пусто
4. Пройди капчу, нажми **"create app"**
5. Скопируй:
   - **client_id** — короткая строка прямо под названием приложения
   - **client_secret** — поле "secret"

### Шаг 3: Вставить в .env

```
REDDIT_CLIENT_ID=твой_client_id
REDDIT_CLIENT_SECRET=твой_client_secret
REDDIT_USER_AGENT=reddit-miner/1.0 by /u/твой_юзернейм
```

Лимит Reddit API: 600 запросов / 10 минут (бесплатно, без карты).
В config.json стоит `reddit_api_limit: 100` для тестов — потом можно поднять до 580.

---

## Получение Anthropic API ключа

1. Зарегистрируйся на https://console.anthropic.com
2. Settings → API Keys → Create Key
3. Вставь в `.env`:
```
ANTHROPIC_API_KEY=sk-ant-...
```

Примерная стоимость: **$1-3/месяц** при ежедневном запуске.
- Haiku (W0, W2) — ~$0.001/запрос
- Sonnet (W3 дайджест) — ~$0.01/запрос

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
python3 -m workers.w1_parser           # спарсить посты из Reddit
python3 -m workers.w2_analyzer         # извлечь боли через Claude Haiku
python3 -m workers.w3_digest           # сгенерить идеи через Claude Sonnet
python3 -m workers.w4_reparse          # напомнить о старых сабреддитах
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
Ночь 02:00  →  W1 парсит Reddit (новые посты с топ-апвоутами)
      03:00  →  W2 через Claude Haiku ищет боли пользователей в постах
      04:00  →  W3 через Claude Sonnet генерит бизнес-идеи → БД + Telegram
      05:00  →  W4 проверяет какие сабреддиты давно не парсились → напоминания
Утро        →  Открываешь localhost:3000, смотришь свежие идеи
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
