import json
import os
import httpx
from datetime import datetime
from workers.helpers import load_config, load_env, setup_logger, claude_call
from workers.db import get_conn


def is_duplicate(new_title, existing_titles, threshold):
    new_words = set(w for w in new_title.lower().split() if len(w) > 4)
    if not new_words:
        return False
    for existing in existing_titles:
        ex_words = set(w for w in existing.lower().split() if len(w) > 4)
        overlap = len(new_words & ex_words) / len(new_words)
        if overlap >= threshold:
            return True
    return False


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


def run():
    config = load_config()
    load_env()
    logger = setup_logger("w3")
    conn = get_conn()
    topic = config["topic"]

    problems = conn.execute(
        """SELECT problem, subreddit, upvotes, source_url
        FROM problems
        WHERE parsed_at >= datetime('now', '-7 days')
        ORDER BY upvotes DESC
        LIMIT 200"""
    ).fetchall()

    if not problems:
        logger.info("W3: no recent problems found")
        return

    problems_list = "\n".join(
        f"- {p['problem']} | r/{p['subreddit']} | ↑{p['upvotes']} | {p['source_url']}"
        for p in problems
    )

    prompt = f"""You are an expert at finding business ideas. You analyze real Reddit user pain points.
Research topic: {topic}

User pain points:
{problems_list}

Find product ideas that solve these pains. Be strict with scoring:
score 9-10 only for truly outstanding ideas with large market potential.
Minimum {config['digest_min_ideas']} ideas even if scores are below threshold.
Include ALL ideas with score >= {config['idea_score_threshold']}.

Return ONLY JSON, no markdown:
[{{
  "title": "name",
  "description": "2-3 sentences: what pain, what solution",
  "product_example": "specifically what the product would look like",
  "score": 8,
  "market_score": 7,
  "difficulty_score": 4,
  "uniqueness_score": 8,
  "source_subreddits": ["subreddit1", "subreddit2"],
  "source_urls": ["url1", "url2"]
}}]"""

    raw = claude_call("claude-sonnet-4-6-20250514", prompt, config, logger)
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
    ideas = json.loads(raw)

    # Deduplication against last 30 days
    existing = conn.execute(
        "SELECT title FROM ideas WHERE created_at >= datetime('now', '-30 days')"
    ).fetchall()
    existing_titles = [r["title"] for r in existing]

    saved_ideas = []
    for idea in ideas:
        dup = is_duplicate(
            idea["title"],
            existing_titles,
            config["idea_dedup_similarity_threshold"],
        )
        conn.execute(
            """INSERT INTO ideas (topic, title, description, product_example, score,
                             market_score, difficulty_score, uniqueness_score,
                             source_urls, subreddits, is_duplicate)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                topic,
                idea["title"],
                idea["description"],
                idea["product_example"],
                idea["score"],
                idea["market_score"],
                idea["difficulty_score"],
                idea["uniqueness_score"],
                json.dumps(idea.get("source_urls", [])),
                json.dumps(idea.get("source_subreddits", [])),
                1 if dup else 0,
            ),
        )

        if not dup:
            saved_ideas.append(idea)
            for sub_name in idea.get("source_subreddits", []):
                conn.execute(
                    """UPDATE subreddits SET weight = weight + ?, total_ideas = total_ideas + 1
                    WHERE name = ?""",
                    (idea["score"] * 0.1, sub_name),
                )

        existing_titles.append(idea["title"])

    # Save digest
    conn.execute(
        "INSERT INTO digests (topic, ideas_json) VALUES (?, ?)",
        (topic, json.dumps(saved_ideas, ensure_ascii=False)),
    )
    conn.commit()

    # Telegram message
    if saved_ideas:
        lines = [
            f"\U0001f50d Дайджест: {topic}",
            f"\U0001f4c5 {datetime.now().strftime('%Y-%m-%d')}",
            f"\U0001f4a1 Найдено идей: {len(saved_ideas)}",
            "",
            "━━━━━━━━━━━━━━━",
        ]
        for idea in saved_ideas:
            lines.append(f"⭐ {idea['score']}/10  {idea['title']}")
            lines.append(idea["description"])
            lines.append(f"→ {idea['product_example']}")
            lines.append(
                f"\U0001f4ca Рынок {idea['market_score']}/10 · Сложность {idea['difficulty_score']}/10 · Уникальность {idea['uniqueness_score']}/10"
            )
            lines.append(
                f"\U0001f4cc Источники: {', '.join(idea.get('source_subreddits', []))}"
            )
            lines.append("━━━━━━━━━━━━━━━")
        msg = "\n".join(lines)
        if send_telegram(msg, logger):
            conn.execute(
                "UPDATE digests SET sent_to_tg=1 WHERE id=(SELECT MAX(id) FROM digests)"
            )
            conn.commit()

    conn.close()
    logger.info(
        f"W3: generated {len(saved_ideas)} ideas, {len(ideas) - len(saved_ideas)} duplicates skipped"
    )


if __name__ == "__main__":
    run()
