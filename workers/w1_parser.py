import os
import time
import json
import httpx
from datetime import datetime, timezone
from workers.helpers import load_config, load_env, setup_logger
from workers.db import use_conn


class RedditAuth:
    def __init__(self):
        self.token = None
        self.expires_at = 0

    def get_token(self):
        if time.time() >= self.expires_at:
            self._refresh()
        return self.token

    def _refresh(self):
        try:
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
        except Exception as e:
            logger = setup_logger("w1")
            logger.error(f"W1: RedditAuth._refresh failed: {e}")
            raise RuntimeError(f"Failed to refresh Reddit access token: {e}") from e


def _reddit_get(url: str, headers: dict, logger) -> httpx.Response:
    """GET wrapper that handles 429 rate-limit responses and proactive rate-limit headers."""
    while True:
        # Proactive check: if the API says we have no remaining calls, wait until reset
        resp = httpx.get(url, headers=headers, timeout=15)

        remaining = resp.headers.get("X-Ratelimit-Remaining")
        reset = resp.headers.get("X-Ratelimit-Reset")

        if remaining is not None:
            try:
                if float(remaining) == 0 and reset is not None:
                    wait = float(reset)
                    logger.warning(f"W1: X-Ratelimit-Remaining=0, sleeping {wait:.1f}s until reset")
                    time.sleep(wait)
            except ValueError:
                pass

        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After")
            wait = float(retry_after) if retry_after is not None else 60.0
            logger.warning(f"W1: 429 rate-limited, sleeping {wait:.1f}s (Retry-After={retry_after})")
            time.sleep(wait)
            continue

        return resp


def run():
    config = load_config()
    load_env()
    logger = setup_logger("w1")
    auth = RedditAuth()
    topic = config["topic"]

    with use_conn() as conn:
        subs = conn.execute(
            """SELECT name FROM subreddits
            WHERE active=1 AND topic=?
            ORDER BY queue_reparse DESC, last_parsed_at ASC NULLS FIRST, weight DESC""",
            (topic,),
        ).fetchall()

        api_calls = 0
        api_limit = config.get("reddit_api_limit", 100)
        total_posts = 0
        ua = os.environ["REDDIT_USER_AGENT"]

        for sub_row in subs:
            sub = sub_row["name"]
            if api_calls >= api_limit:
                logger.info(f"W1: API limit ({api_limit}) approaching, stopping")
                break

            try:
                headers = {"Authorization": f"Bearer {auth.get_token()}", "User-Agent": ua}
                resp = _reddit_get(
                    f"https://oauth.reddit.com/r/{sub}/top.json?t=week&limit={config['reddit_posts_per_request']}",
                    headers=headers,
                    logger=logger,
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
                        cresp = _reddit_get(
                            f"https://oauth.reddit.com/r/{sub}/comments/{p['id']}.json?limit=10&sort=top&depth=1",
                            headers=headers,
                            logger=logger,
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

                    if api_calls >= api_limit:
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
                    (datetime.now(timezone.utc).isoformat(), sub),
                )
                conn.commit()

            except Exception as e:
                logger.error(f"W1: error parsing r/{sub}: {e}")
                continue

        conn.commit()

    logger.info(
        f"W1: parsed {total_posts} posts from {len(subs)} subreddits, {api_calls} API calls"
    )


if __name__ == "__main__":
    run()
