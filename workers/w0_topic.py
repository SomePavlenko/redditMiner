import hashlib
import json
import os
import httpx
from workers.helpers import load_config, setup_logger, claude_call, load_env, ROOT
from workers.db import get_conn

TOPIC_HASH_FILE = os.path.join(ROOT, ".topic_hash")


def get_topic_hash(topic):
    return hashlib.md5(topic.encode()).hexdigest()


def topic_changed(topic):
    current_hash = get_topic_hash(topic)
    if os.path.exists(TOPIC_HASH_FILE):
        with open(TOPIC_HASH_FILE) as f:
            return f.read().strip() != current_hash
    return True


def save_topic_hash(topic):
    with open(TOPIC_HASH_FILE, "w") as f:
        f.write(get_topic_hash(topic))


def fetch_claude_subreddits(topic, config, logger):
    prompt = f"""Find the top 20 subreddits on Reddit for discovering business ideas related to '{topic}'.
Return ONLY a JSON array, no markdown: [{{"name": "subredditname", "estimated_members": 100000, "relevance_score": 9}}]
Sort by relevance_score DESC. Use real subreddit names without r/ prefix."""
    raw = claude_call("claude-haiku-4-5-20250901", prompt, config, logger)
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
    return json.loads(raw)


def fetch_reddit_subreddits(topic, logger):
    try:
        resp = httpx.get(
            f"https://www.reddit.com/subreddits/search.json?q={topic}&limit=10",
            headers={"User-Agent": "reddit-miner/1.0"},
            timeout=15,
        )
        resp.raise_for_status()
        results = []
        for child in resp.json()["data"]["children"]:
            d = child["data"]
            results.append(
                {
                    "name": d["display_name"],
                    "estimated_members": d.get("subscribers", 0),
                    "relevance_score": 5,
                }
            )
        return results
    except Exception as e:
        logger.warning(f"Reddit search failed: {e}")
        return []


def run(force=False):
    config = load_config()
    load_env()
    topic = config["topic"]
    logger = setup_logger("w0")

    if not force and not topic_changed(topic):
        logger.info(f"W0: topic '{topic}' unchanged, skipping")
        return

    logger.info(f"W0: starting for topic '{topic}'")

    claude_subs = fetch_claude_subreddits(topic, config, logger)
    reddit_subs = fetch_reddit_subreddits(topic, logger)

    # Deduplicate by name (lowercase)
    seen = {}
    for s in claude_subs + reddit_subs:
        key = s["name"].lower()
        if key not in seen or s["relevance_score"] > seen[key]["relevance_score"]:
            seen[key] = s

    merged = sorted(seen.values(), key=lambda x: x["relevance_score"], reverse=True)

    conn = get_conn()
    conn.execute("UPDATE subreddits SET active=0 WHERE topic=?", (topic,))
    for s in merged:
        conn.execute(
            """INSERT INTO subreddits (name, topic, weight, active)
            VALUES (?, ?, ?, 1)
            ON CONFLICT(name) DO UPDATE SET topic=?, weight=?, active=1""",
            (s["name"], topic, s["relevance_score"], topic, s["relevance_score"]),
        )
    conn.commit()
    conn.close()

    save_topic_hash(topic)
    logger.info(f"W0: found {len(merged)} subreddits for topic '{topic}'")


if __name__ == "__main__":
    import sys
    run(force="--force" in sys.argv)
