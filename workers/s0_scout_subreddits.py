"""
S0 — Разведка сабреддитов.
Находит сабреддиты по теме через Claude API или вручную.

Режимы:
  python3 -m workers.s0_scout_subreddits                                      # авто через Claude API
  python3 -m workers.s0_scout_subreddits --add jobs,resumes,careerguidance    # вручную
  python3 -m workers.s0_scout_subreddits --force                               # принудительно обновить
"""

import hashlib
import json
import os
import sys
import httpx
from workers.helpers import load_config, load_env, setup_logger, claude_call, parse_json_response, ROOT
from prompts import S0_FIND_SUBREDDITS
from workers.db import use_conn

TOPIC_HASH_FILE = os.path.join(ROOT, ".topic_hash")


def get_topic_hash(topic):
    return hashlib.md5(topic.encode()).hexdigest()


def topic_changed(topic):
    if os.path.exists(TOPIC_HASH_FILE):
        with open(TOPIC_HASH_FILE) as f:
            return f.read().strip() != get_topic_hash(topic)
    return True


def save_topic_hash(topic):
    with open(TOPIC_HASH_FILE, "w") as f:
        f.write(get_topic_hash(topic))


def add_subreddits(names, topic, logger):
    """Добавить сабреддиты в БД (без деактивации существующих)."""
    added = 0
    with use_conn() as conn:
        for name in names:
            name = name.strip().lower()
            if not name:
                continue
            conn.execute(
                """INSERT INTO subreddits (name, topic, weight, active)
                VALUES (?, ?, 5, 1)
                ON CONFLICT(name) DO UPDATE SET topic=?, active=1""",
                (name, topic, topic),
            )
            added += 1
        conn.commit()

    save_topic_hash(topic)
    logger.info(f"S0: added {added} subreddits for topic '{topic}'")
    return added


def find_subreddits_via_api(topic, config, logger):
    """Находит сабреддиты через Claude API."""
    load_env()

    prompt = S0_FIND_SUBREDDITS.format(topic=topic)

    raw = claude_call(config["claude_model_fast"], prompt, config, logger)
    subs = parse_json_response(raw, logger)
    return subs


def fetch_reddit_subreddits(topic, logger):
    """Дополнительный поиск через публичный Reddit JSON."""
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
            results.append({
                "name": d["display_name"],
                "relevance_score": 5,
            })
        return results
    except Exception as e:
        logger.warning(f"S0: Reddit search failed: {e}")
        return []


def show_status(topic, logger):
    """Показать текущие сабреддиты."""
    with use_conn() as conn:
        subs = conn.execute(
            "SELECT name, last_parsed_at, total_ideas, active FROM subreddits WHERE topic=? AND active=1 ORDER BY weight DESC",
            (topic,),
        ).fetchall()

    if not subs:
        print(f"Нет сабреддитов для темы '{topic}'")
        return False

    print(f"\nСабреддиты для темы '{topic}' ({len(subs)} шт):")
    for s in subs:
        parsed = s["last_parsed_at"] or "—"
        print(f"  r/{s['name']} | parsed: {parsed} | ideas: {s['total_ideas']}")
    return True


def run(force=False):
    config = load_config()
    topic = config["topic"]
    logger = setup_logger("s0")

    # Ручной режим: --add
    if "--add" in sys.argv:
        idx = sys.argv.index("--add")
        if idx + 1 < len(sys.argv):
            names = sys.argv[idx + 1].split(",")
            add_subreddits(names, topic, logger)
            show_status(topic, logger)
            return
        else:
            print("Использование: python3 -m workers.s0_scout_subreddits --add jobs,resumes")
            return

    # Проверяем: тема не менялась и сабреддиты есть?
    if not force and not topic_changed(topic):
        has_subs = show_status(topic, logger)
        if has_subs:
            logger.info(f"S0: topic unchanged, subreddits exist")
            return

    # Автоматический поиск через Claude API + Reddit
    logger.info(f"S0: searching subreddits for topic '{topic}'")

    try:
        claude_subs = find_subreddits_via_api(topic, config, logger)
    except json.JSONDecodeError as e:
        logger.error(f"S0: Claude returned invalid JSON: {e}")
        claude_subs = []
    except Exception as e:
        logger.error(f"S0: Claude API failed: {e}")
        claude_subs = []

    reddit_subs = fetch_reddit_subreddits(topic, logger)

    # Объединяем и дедуплицируем
    seen = {}
    for s in claude_subs + reddit_subs:
        key = s["name"].lower()
        if key not in seen or s.get("relevance_score", 0) > seen[key].get("relevance_score", 0):
            seen[key] = s

    if not seen:
        logger.error("S0: no subreddits found")
        print("Не удалось найти сабреддиты. Добавьте вручную: --add jobs,resumes")
        return

    merged = sorted(seen.values(), key=lambda x: x.get("relevance_score", 0), reverse=True)
    names = [s["name"] for s in merged]
    add_subreddits(names, topic, logger)

    show_status(topic, logger)
    print(f"\nS0: найдено {len(names)} сабреддитов")


if __name__ == "__main__":
    run(force="--force" in sys.argv)
