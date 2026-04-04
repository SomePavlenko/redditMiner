"""
S1 — Reddit Parser. Два шага:
  S1a: python3 -m workers.s1_fetch_reddit posts     — получить посты (1 запрос/сабреддит)
  S1b: python3 -m workers.s1_fetch_reddit comments  — получить комменты к топ постам
  python3 -m workers.s1_fetch_reddit                 — оба шага последовательно
"""

import sys
import time
import json
import httpx
from datetime import datetime, timezone
from workers.helpers import load_config, load_env, setup_logger
from workers.trimmer import trim_posts, trim_comments
from workers.db import use_conn

HEADERS = {"User-Agent": "reddit-miner/1.0 personal research tool"}


def _reddit_get(url, params, logger):
    """GET запрос с обработкой 429."""
    r = httpx.get(url, params=params, headers=HEADERS, timeout=15)
    if r.status_code == 429:
        wait = float(r.headers.get("Retry-After", 60))
        logger.warning(f"W1: 429 rate-limited, sleeping {wait}s")
        time.sleep(wait)
        r = httpx.get(url, params=params, headers=HEADERS, timeout=15)
    return r


def fetch_posts():
    """W1a: получить посты из сабреддитов, обрезать через trimmer, сохранить в БД."""
    config = load_config()
    load_env()
    logger = setup_logger("s1")
    topic = config["topic"]

    with use_conn() as conn:
        subs = conn.execute(
            """SELECT name FROM subreddits
            WHERE active=1 AND topic=?
            ORDER BY queue_reparse DESC, last_parsed_at ASC NULLS FIRST, weight DESC""",
            (topic,),
        ).fetchall()

        if not subs:
            logger.info("W1a: no subreddits to parse")
            print("Нет сабреддитов. Сначала запусти W0.")
            return

        api_calls = 0
        api_limit = config.get("reddit_api_limit", 55)
        total_posts = 0

        for sub_row in subs:
            sub = sub_row["name"]
            if api_calls >= api_limit:
                logger.info(f"W1a: API limit ({api_limit}) reached")
                break

            logger.info(f"W1a: fetching r/{sub} posts...")
            try:
                r = _reddit_get(
                    f"https://www.reddit.com/r/{sub}/top.json",
                    {"t": "week", "limit": str(config["reddit_posts_per_request"])},
                    logger,
                )
                api_calls += 1
                r.raise_for_status()

                raw_children = r.json()["data"]["children"]
                clean_posts = trim_posts(raw_children, config)

                for post in clean_posts:
                    try:
                        conn.execute(
                            """INSERT OR IGNORE INTO raw_posts
                            (reddit_id, subreddit, topic, title, body, url, upvotes, parsed_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                            (
                                post["reddit_id"], sub, topic, post["title"],
                                post["body"], post["url"], post["upvotes"],
                                datetime.now(timezone.utc).isoformat(),
                            ),
                        )
                        total_posts += 1
                    except Exception as e:
                        logger.warning(f"W1a: insert failed: {e}")

                conn.execute(
                    "UPDATE subreddits SET last_parsed_at=?, queue_reparse=0 WHERE name=?",
                    (datetime.now(timezone.utc).isoformat(), sub),
                )
                conn.commit()
                logger.info(f"W1a: r/{sub} → {len(clean_posts)} posts")

            except Exception as e:
                logger.error(f"W1a: error on r/{sub}: {e}")

            time.sleep(1.1)

    logger.info(f"W1a: total {total_posts} posts, {api_calls} API calls")
    print(f"W1a: сохранено {total_posts} постов из {len(subs)} сабреддитов")


def fetch_comments():
    """W1b: получить комменты к топ постам, обрезать через trimmer, дописать в БД."""
    config = load_config()
    load_env()
    logger = setup_logger("s1")
    topic = config["topic"]
    top_n = config.get("posts_for_comments_n", 15)

    with use_conn() as conn:
        posts = conn.execute(
            """SELECT id, reddit_id, subreddit FROM raw_posts
            WHERE comments_fetched=0 AND (topic=? OR topic='')
            ORDER BY upvotes DESC
            LIMIT ?""",
            (topic, top_n),
        ).fetchall()

        if not posts:
            logger.info("W1b: no posts need comments")
            print("Нет постов для загрузки комментариев")
            return

        api_calls = 0
        api_limit = config.get("reddit_api_limit", 55)

        for post in posts:
            if api_calls >= api_limit:
                logger.info(f"W1b: API limit ({api_limit}) reached")
                break

            logger.info(f"W1b: fetching comments for {post['reddit_id']}...")
            try:
                r = _reddit_get(
                    f"https://www.reddit.com/r/{post['subreddit']}/comments/{post['reddit_id']}.json",
                    {"limit": "20", "sort": "top", "depth": "1"},
                    logger,
                )
                api_calls += 1
                r.raise_for_status()

                clean_comments = trim_comments(r.json(), config)

                conn.execute(
                    "UPDATE raw_posts SET comments_json=?, comments_fetched=1 WHERE id=?",
                    (json.dumps(clean_comments, ensure_ascii=False), post["id"]),
                )
                conn.commit()
                logger.info(f"W1b: post {post['reddit_id']} → {len(clean_comments)} comments")

            except Exception as e:
                logger.error(f"W1b: error on {post['reddit_id']}: {e}")

            time.sleep(1.1)

    logger.info(f"W1b: fetched comments for {len(posts)} posts, {api_calls} API calls")
    print(f"W1b: загружены комментарии к {len(posts)} постам")


def run():
    args = sys.argv[1:] if len(sys.argv) > 1 else []

    if "posts" in args:
        fetch_posts()
    elif "comments" in args:
        fetch_comments()
    else:
        fetch_posts()
        fetch_comments()


if __name__ == "__main__":
    run()
