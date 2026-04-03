import os
import time
import json
import httpx
from datetime import datetime
from workers.helpers import load_config, load_env, setup_logger
from workers.db import get_conn


class RedditAuth:
    def __init__(self):
        self.token = None
        self.expires_at = 0

    def get_token(self):
        if time.time() >= self.expires_at:
            self._refresh()
        return self.token

    def _refresh(self):
        resp = httpx.post(
            "https://www.reddit.com/api/v1/access_token",
            auth=(os.environ["REDDIT_CLIENT_ID"], os.environ["REDDIT_CLIENT_SECRET"]),
            data={"grant_type": "client_credentials"},
            headers={"User-Agent": os.environ["REDDIT_USER_AGENT"]},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        self.token = data["access_token"]
        self.expires_at = time.time() + data["expires_in"] - 60


def run():
    config = load_config()
    load_env()
    logger = setup_logger("w1")
    auth = RedditAuth()
    conn = get_conn()
    topic = config["topic"]

    subs = conn.execute(
        """SELECT name FROM subreddits
        WHERE active=1 AND topic=?
        ORDER BY queue_reparse DESC, last_parsed_at ASC NULLS FIRST, weight DESC""",
        (topic,),
    ).fetchall()

    api_calls = 0
    total_posts = 0
    ua = os.environ["REDDIT_USER_AGENT"]

    for sub_row in subs:
        sub = sub_row["name"]
        if api_calls >= 580:
            logger.info("W1: API limit approaching, stopping")
            break

        try:
            headers = {"Authorization": f"Bearer {auth.get_token()}", "User-Agent": ua}
            resp = httpx.get(
                f"https://oauth.reddit.com/r/{sub}/top.json?t=week&limit={config['reddit_posts_per_request']}",
                headers=headers,
                timeout=15,
            )
            api_calls += 1
            resp.raise_for_status()
            posts = resp.json()["data"]["children"]

            for post_data in posts:
                p = post_data["data"]
                if p.get("promoted"):
                    continue
                if p.get("ups", 0) < config["min_upvotes"]:
                    continue

                comments_json = None
                try:
                    cresp = httpx.get(
                        f"https://oauth.reddit.com/r/{sub}/comments/{p['id']}.json?limit=10&sort=top&depth=1",
                        headers=headers,
                        timeout=15,
                    )
                    api_calls += 1
                    cresp.raise_for_status()
                    comment_listing = cresp.json()
                    if len(comment_listing) > 1:
                        comments = [
                            c["data"].get("body", "")
                            for c in comment_listing[1]["data"]["children"]
                            if c["kind"] == "t1"
                        ]
                        comments_json = json.dumps(comments[:10])
                except Exception as e:
                    logger.warning(f"W1: failed to fetch comments for {p['id']}: {e}")

                if api_calls >= 580:
                    break

                try:
                    conn.execute(
                        """INSERT OR IGNORE INTO raw_posts
                        (reddit_id, subreddit, title, body, url, upvotes, comments_json)
                        VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (
                            p["id"],
                            sub,
                            p.get("title", ""),
                            p.get("selftext", ""),
                            f"https://reddit.com{p.get('permalink', '')}",
                            p.get("ups", 0),
                            comments_json,
                        ),
                    )
                    total_posts += 1
                except Exception as e:
                    logger.warning(f"W1: insert failed for {p['id']}: {e}")

            conn.execute(
                "UPDATE subreddits SET last_parsed_at=?, queue_reparse=0 WHERE name=?",
                (datetime.utcnow().isoformat(), sub),
            )
            conn.commit()

        except Exception as e:
            logger.error(f"W1: error parsing r/{sub}: {e}")
            continue

    conn.commit()
    conn.close()
    logger.info(
        f"W1: parsed {total_posts} posts from {len(subs)} subreddits, {api_calls} API calls"
    )


if __name__ == "__main__":
    run()
