# Reddit Miner — контекст проекта

## Что это
Автономная система поиска бизнес-идей через парсинг болей пользователей Reddit.
Запускается ночью по cron, результаты приходят в Telegram утром.

## Стек
- Python 3.11+ — все воркеры и FastAPI
- SQLite (WAL mode) — основная БД, файл data/miner.db
- React + Vite + Tailwind + Recharts — фронтенд на localhost:3000
- FastAPI — REST API на localhost:8000
- Claude API: Haiku для батчей (дёшево), Sonnet для дайджеста (качество)
- Reddit OAuth2 client_credentials — без логина пользователя

## Воркеры и порядок запуска
1. W0 — topic agent (разово при смене topic в config.json)
2. W1 — parser (02:00 по cron)
3. W2 — analyzer (03:00 по cron)
4. W3 — digest + Telegram (04:00 по cron)
5. W4 — reparse suggestions (05:00 по cron)

Для первого запуска: python workers/run_all.py

## Важные соглашения
- Все параметры только из config.json и .env, никаких хардкодов
- Каждый воркер логирует в logs/{worker}_{date}.log
- SQLite WAL mode включён при инициализации БД
- Claude API вызовы: retry 3 раза с backoff 2s
- Reddit OAuth токен: автоматический refresh при истечении (expires_in - 60s)
- W0 определяет смену topic через MD5 hash в файле .topic_hash

## Статус разработки
- [x] Структура папок и БД
- [x] W0 topic agent
- [x] W1 parser
- [x] W2 analyzer
- [x] W3 digest + TG
- [x] W4 reparse
- [x] FastAPI
- [x] React frontend
- [x] setup.sh + cron
