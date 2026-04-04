import os
import time
import json
import httpx
from datetime import datetime, timezone
from workers.helpers import load_config, load_env, setup_logger
from workers.db import use_conn

HEADERS = {
    "User-Agent": "reddit-miner/1.0 personal research tool"
}


def fetch_subreddit_top(subreddit, config, logger):
    url = f"https://www.reddit.com/r/{subreddit}/top.json"
    params = {"t": "week", "limit": str(config["reddit_posts_per_request"])}
    min_upvotes = config["min_upvotes"]

    try:
        r = httpx.get(url, params=params, headers=HEADERS, timeout=15)
        if r.status_code == 429:
            retry_after = float(r.headers.get("Retry-After", 60))
            logger.warning(f"W1: 429 rate-limited on r/{subreddit}, sleeping {retry_after}s")
            time.sleep(retry_after)
            r = httpx.get(url, params=params, headers=HEADERS, timeout=15)
        r.raise_for_status()
        posts = r.json()["data"]["children"]

        result = []
        for post in posts:
            d = post["data"]
            if d.get("ups", 0) < min_upvotes:
                continue
            if d.get("promoted") or d.get("is_reddit_media_domain"):
                continue

            result.append({
                "reddit_id": d["id"],
                "subreddit": subreddit,
                "title": d.get("title", ""),
                "body": d.get("selftext", "")[:500],
                "url": f"https://reddit.com{d.get('permalink', '')}",
                "upvotes": d.get("ups", 0),
            })

        return result
    except Exception as e:
        logger.error(f"W1: error fetching r/{subreddit}: {e}")
        return []


def fetch_comments(subreddit, post_id, logger):
    url = f"https://www.reddit.com/r/{subreddit}/comments/{post_id}.json"
    params = {"limit": "10", "sort": "top", "depth": "1"}

    try:
        r = httpx.get(url, params=params, headers=HEADERS, timeout=15)
        if r.status_code == 429:
            retry_after = float(r.headers.get("Retry-After", 60))
            logger.warning(f"W1: 429 rate-limited on comments {post_id}, sleeping {retry_after}s")
            time.sleep(retry_after)
            r = httpx.get(url, params=params, headers=HEADERS, timeout=15)
        r.raise_for_status()
        data = r.json()

        comments = []
        if len(data) > 1:
            for item in data[1]["data"]["children"]:
                d = item.get("data", {})
                body = d.get("body", "")
                if body and body != "[deleted]" and body != "[removed]":
                    comments.append({
                        "text": body[:300],
                        "ups": d.get("ups", 0),
                    })
        return comments
    except Exception as e:
        logger.warning(f"W1: error fetching comments for {post_id}: {e}")
        return []


def run():
    config = load_config()
    load_env()
    logger = setup_logger("w1")
    topic = config["topic"]

    with use_conn() as conn:
        subs = conn.execute(
            """SELECT name FROM subreddits
            WHERE active=1 AND topic=?
            ORDER BY queue_reparse DESC, last_parsed_at ASC NULLS FIRST, weight DESC""",
            (topic,),
        ).fetchall()

        api_calls = 0
        api_limit = config.get("reddit_api_limit", 55)
        total_posts = 0

        for sub_row in subs:
            sub = sub_row["name"]
            if api_calls >= api_limit:
                logger.info(f"W1: API limit ({api_limit}) reached, stopping")
                break

            logger.info(f"W1: parsing r/{sub}...")
            posts = fetch_subreddit_top(sub, config, logger)
            api_calls += 1
            time.sleep(1.1)

            for post in posts:
                if api_calls >= api_limit:
                    break

                comments = fetch_comments(sub, post["reddit_id"], logger)
                api_calls += 1
                time.sleep(1.1)

                try:
                    conn.execute(
                        """INSERT OR IGNORE INTO raw_posts
                        (reddit_id, subreddit, title, body, url, upvotes, comments_json, parsed_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            post["reddit_id"],
                            post["subreddit"],
                            post["title"],
                            post["body"],
                            post["url"],
                            post["upvotes"],
                            json.dumps(comments),
                            datetime.now(timezone.utc).isoformat(),
                        ),
                    )
                    total_posts += 1
                except Exception as e:
                    logger.warning(f"W1: insert failed for {post['reddit_id']}: {e}")

            conn.execute(
                "UPDATE subreddits SET last_parsed_at=?, queue_reparse=0 WHERE name=?",
                (datetime.now(timezone.utc).isoformat(), sub),
            )
            conn.commit()

    logger.info(f"W1: parsed {total_posts} posts from {len(subs)} subreddits, {api_calls} API calls")


if __name__ == "__main__":
    run()
