#!/bin/bash
set -e

echo "=== Reddit Miner Setup ==="

# Python зависимости
pip install anthropic httpx fastapi uvicorn python-dotenv python-telegram-bot aiofiles

# Frontend
cd frontend && npm install && cd ..

# Создать папки
mkdir -p data logs

# Инициализировать БД
python3 -c "
import sys
sys.path.insert(0, '.')
from workers.db import init_db
init_db()
print('DB initialized')
"

# Cron задачи (добавить если ещё нет)
PROJ=$(pwd)
add_cron() {
  (crontab -l 2>/dev/null | grep -v "$2"; echo "$1 cd $PROJ && python3 $2 >> $PROJ/logs/cron.log 2>&1") | crontab -
}

add_cron "0 2 * * *" "workers/w1_parser.py"
add_cron "0 3 * * *" "workers/w2_analyzer.py"
add_cron "0 4 * * *" "workers/w3_digest.py"
add_cron "0 5 * * *" "workers/w4_reparse.py"

echo ""
echo "=== Setup complete! ==="
echo ""
echo "Следующие шаги:"
echo "1. Заполни .env (скопируй из .env.example)"
echo "2. Запусти API:     uvicorn api.main:app --reload"
echo "3. Запусти фронт:   cd frontend && npm run dev"
echo "4. Первый запуск:   python3 workers/run_all.py"
echo ""
echo "Фронт: http://localhost:3000"
echo "API:   http://localhost:8000/docs"
