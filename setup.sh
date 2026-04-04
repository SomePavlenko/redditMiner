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

# Cron: один job запускает весь пайплайн
PROJ=$(pwd)
(crontab -l 2>/dev/null | grep -v "run_pipeline"; echo "0 2 * * * cd $PROJ && python3 -m workers.run_pipeline >> $PROJ/logs/cron.log 2>&1") | crontab -

echo ""
echo "=== Setup complete! ==="
echo ""
echo "Следующие шаги:"
echo "1. Заполни .env (ANTHROPIC_API_KEY обязателен)"
echo "2. Добавь сабреддиты: python3 -m workers.s0_scout_subreddits --add jobs,resumes"
echo "3. Запусти API:       python3 -m uvicorn api.main:app --reload --port 8000"
echo "4. Запусти фронт:     cd frontend && npm run dev"
echo "5. Первый запуск:     python3 -m workers.run_pipeline"
echo ""
echo "Фронт: http://localhost:3000"
echo "API:   http://localhost:8000/docs"
