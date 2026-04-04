import json
import os
import httpx
from datetime import datetime, timedelta
from pathlib import Path
from workers.helpers import load_config, load_env, setup_logger
from workers.db import use_conn


def send_telegram(message, logger):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        logger.warning("W3: Telegram credentials not configured, skipping send")
        return False
    try:
        resp = httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"},
            timeout=15,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"W3: Telegram send failed: {e}")
        return False


def prepare_digest_context():
    config = load_config()
    logger = setup_logger("w3")
    topic = config["topic"]

    with use_conn() as conn:
        problems = conn.execute(
            """SELECT problem, subreddit, upvotes, source_url
            FROM problems
            WHERE parsed_at >= datetime('now', '-7 days')
            ORDER BY upvotes DESC
            LIMIT 200"""
        ).fetchall()

    if not problems:
        logger.info("W3: no recent problems found")
        print("Нет болей за последние 7 дней")
        return None

    context = {
        "topic": topic,
        "date": datetime.now().strftime("%Y-%m-%d"),
        "total_problems": len(problems),
        "idea_score_threshold": config["idea_score_threshold"],
        "digest_min_ideas": config["digest_min_ideas"],
        "problems": [
            {
                "problem": p["problem"],
                "upvotes": p["upvotes"],
                "subreddit": p["subreddit"],
                "url": p["source_url"],
            }
            for p in problems
        ],
    }

    Path("data").mkdir(exist_ok=True)
    with open("data/digest_context.json", "w", encoding="utf-8") as f:
        json.dump(context, f, ensure_ascii=False, indent=2)

    logger.info(f"W3: prepared digest context with {len(problems)} problems")
    print(f"Контекст готов: data/digest_context.json ({len(problems)} болей)")
    print(f"\nТеперь запусти Claude Code:")
    print(f'  claude')
    print(f'  > "Прочитай data/digest_context.json и сгенерируй топ идей для продуктов"')

    return "data/digest_context.json"


def run():
    prepare_digest_context()


if __name__ == "__main__":
    run()
