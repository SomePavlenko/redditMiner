import os
import httpx
from workers.helpers import load_config, load_env, setup_logger
from workers.db import get_conn


def send_telegram(message, logger):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        logger.warning("W4: Telegram not configured")
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
        logger.error(f"W4: Telegram failed: {e}")
        return False


def run():
    config = load_config()
    load_env()
    logger = setup_logger("w4")
    conn = get_conn()

    subs = conn.execute(
        """SELECT name, total_ideas FROM subreddits
        WHERE total_ideas > 0
        AND last_parsed_at <= datetime('now', ? || ' days')
        AND queue_reparse = 0 AND active = 1""",
        (f"-{config['reparse_days']}",),
    ).fetchall()

    sent = 0
    for sub in subs:
        top_idea = conn.execute(
            """SELECT title, score FROM ideas
            WHERE subreddits LIKE ? ORDER BY score DESC LIMIT 1""",
            (f'%{sub["name"]}%',),
        ).fetchone()

        if top_idea:
            msg = (
                f"\U0001f4cc Пора перепарсить: r/{sub['name']}\n"
                f"Неделю назад здесь нашли {sub['total_ideas']} идей\n"
                f"Лучшая: {top_idea['title']} (⭐{top_idea['score']})\n"
                f"Добавить в очередь? → /reparse_{sub['name']}"
            )
            if send_telegram(msg, logger):
                sent += 1

    conn.close()
    logger.info(f"W4: sent {sent} reparse reminders")


if __name__ == "__main__":
    run()
