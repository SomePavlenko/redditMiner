"""
S6 — Проверка перепарсинга сабреддитов.
Находит сабреддиты которые давно не парсились и у которых были хорошие идеи.
Отправляет напоминания в Telegram.

python3 -m workers.s6_reparse_check
"""

import os
import httpx
from workers.helpers import load_config, load_env, setup_logger
from workers.db import use_conn


def send_telegram(message, logger):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        logger.warning("S6: Telegram not configured")
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
        logger.error(f"S6: Telegram failed: {e}")
        return False


def run():
    config = load_config()
    load_env()
    logger = setup_logger("s6")

    with use_conn() as conn:
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
                (f'%"{sub["name"]}"%',),
            ).fetchone()

            if top_idea:
                msg = (
                    f"📌 Пора перепарсить: r/{sub['name']}\n"
                    f"Ранее нашли {sub['total_ideas']} идей\n"
                    f"Лучшая: {top_idea['title']} (⭐{top_idea['score']})\n"
                )
                if send_telegram(msg, logger):
                    sent += 1

    logger.info(f"S6: sent {sent} reparse reminders")
    print(f"S6: отправлено {sent} напоминаний")


if __name__ == "__main__":
    run()
