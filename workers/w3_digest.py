import json
import os
import httpx
from datetime import datetime
from workers.helpers import load_config, load_env, setup_logger, claude_call, parse_json_response
from workers.db import use_conn


def is_duplicate(new_title, existing_titles, threshold):
    new_words = set(w for w in new_title.lower().split() if len(w) > 3)
    if not new_words:
        return False
    for existing in existing_titles:
        ex_words = set(w for w in existing.lower().split() if len(w) > 3)
        if not ex_words:
            continue
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
            return

        problems_list = "\n".join(
            f"- {p['problem']} | r/{p['subreddit']} | \u2191{p['upvotes']} | {p['source_url']}"
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
        try:
            ideas = parse_json_response(raw, logger)
        except json.JSONDecodeError as e:
            logger.error(f"W3: Claude returned invalid JSON: {e}")
            return

        # Deduplication against last 30 days
        existing = conn.execute(
            "SELECT title FROM ideas WHERE created_at >= datetime('now', '-30 days')"
        ).fetchall()
        existing_titles = [r["title"] for r in existing]

        saved_ideas = []
        for idea in ideas:
            dup = is_duplicate(
                idea.get("title", ""),
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
                    idea.get("title", "Untitled"),
                    idea.get("description", ""),
                    idea.get("product_example", ""),
                    idea.get("score", 0),
                    idea.get("market_score", 0),
                    idea.get("difficulty_score", 0),
                    idea.get("uniqueness_score", 0),
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
                        (idea.get("score", 0) * 0.1, sub_name),
                    )

            existing_titles.append(idea.get("title", ""))

        # Save digest
        conn.execute(
            "INSERT INTO digests (topic, ideas_json) VALUES (?, ?)",
            (topic, json.dumps(saved_ideas, ensure_ascii=False)),
        )
        conn.commit()

        # Telegram message
        if saved_ideas:
            lines = [
                f"\U0001f50d \u0414\u0430\u0439\u0434\u0436\u0435\u0441\u0442: {topic}",
                f"\U0001f4c5 {datetime.now().strftime('%Y-%m-%d')}",
                f"\U0001f4a1 \u041d\u0430\u0439\u0434\u0435\u043d\u043e \u0438\u0434\u0435\u0439: {len(saved_ideas)}",
                "",
                "\u2501" * 15,
            ]
            for idea in saved_ideas:
                lines.append(f"\u2b50 {idea.get('score', 0)}/10  {idea.get('title', '')}")
                lines.append(idea.get("description", ""))
                lines.append(f"\u2192 {idea.get('product_example', '')}")
                lines.append(
                    f"\U0001f4ca \u0420\u044b\u043d\u043e\u043a {idea.get('market_score', 0)}/10 \u00b7 \u0421\u043b\u043e\u0436\u043d\u043e\u0441\u0442\u044c {idea.get('difficulty_score', 0)}/10 \u00b7 \u0423\u043d\u0438\u043a\u0430\u043b\u044c\u043d\u043e\u0441\u0442\u044c {idea.get('uniqueness_score', 0)}/10"
                )
                lines.append(
                    f"\U0001f4cc \u0418\u0441\u0442\u043e\u0447\u043d\u0438\u043a\u0438: {', '.join(idea.get('source_subreddits', []))}"
                )
                lines.append("\u2501" * 15)
            msg = "\n".join(lines)
            if send_telegram(msg, logger):
                conn.execute(
                    "UPDATE digests SET sent_to_tg=1 WHERE id=(SELECT MAX(id) FROM digests)"
                )
                conn.commit()

    logger.info(
        f"W3: generated {len(saved_ideas)} ideas, {len(ideas) - len(saved_ideas)} duplicates skipped"
    )


if __name__ == "__main__":
    run()
