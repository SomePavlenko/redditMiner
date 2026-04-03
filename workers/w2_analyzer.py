import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from workers.helpers import load_config, load_env, setup_logger, claude_call, parse_json_response
from workers.db import use_conn


def build_batch_prompt(posts):
    batch = []
    for p in posts:
        item = {"post_id": p["id"], "title": p["title"], "body": (p["body"] or "")[:500]}
        if p["comments_json"]:
            try:
                item["top_comments"] = json.loads(p["comments_json"])[:5]
            except json.JSONDecodeError:
                pass
        batch.append(item)

    return f"""You analyze Reddit posts to find business opportunities.
For each post, extract ONLY specific user pain points —
things that don't work, that frustrate people, that they want improved.
Ignore vague complaints without specifics and positive posts.

Posts (JSON):
{json.dumps(batch, ensure_ascii=False)}

Return ONLY JSON, no markdown:
[{{"post_id": 123, "problems": ["pain 1", "pain 2"]}}]
If no problems — return empty problems array for that post."""


def process_batch(batch_posts, config, logger):
    prompt = build_batch_prompt(batch_posts)
    raw = claude_call("claude-haiku-4-5-20250901", prompt, config, logger)
    return parse_json_response(raw, logger)


def run():
    config = load_config()
    load_env()
    logger = setup_logger("w2")

    with use_conn() as conn:
        posts = conn.execute(
            """SELECT id, title, body, comments_json, subreddit, upvotes, url
            FROM raw_posts WHERE processed=0 ORDER BY upvotes DESC"""
        ).fetchall()

        if not posts:
            logger.info("W2: no unprocessed posts")
            return

        posts = [dict(p) for p in posts]
        batch_size = config["claude_batch_size"]
        batches = [posts[i : i + batch_size] for i in range(0, len(posts), batch_size)]

        total_problems = 0

        # Process up to 5 batches in parallel using threads
        for chunk_start in range(0, len(batches), 5):
            chunk = batches[chunk_start : chunk_start + 5]
            results = []

            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = {
                    executor.submit(process_batch, b, config, logger): b
                    for b in chunk
                }
                for future in as_completed(futures):
                    batch_posts = futures[future]
                    try:
                        result = future.result()
                        results.append((batch_posts, result))
                    except json.JSONDecodeError as e:
                        logger.error(f"W2: Claude returned invalid JSON for batch: {e}")
                        # Mark posts as processed so we don't retry garbage forever
                        batch_ids = [p["id"] for p in batch_posts]
                        conn.executemany(
                            "UPDATE raw_posts SET processed=1 WHERE id=?",
                            [(pid,) for pid in batch_ids],
                        )
                        conn.commit()
                    except Exception as e:
                        logger.error(f"W2: batch failed: {e}")

            for batch_posts, result in results:
                post_map = {p["id"]: p for p in batch_posts}
                processed_ids = set()
                for item in result:
                    post = post_map.get(item.get("post_id"))
                    if not post:
                        continue
                    processed_ids.add(post["id"])
                    for problem_text in item.get("problems", []):
                        conn.execute(
                            """INSERT INTO problems (raw_post_id, subreddit, problem, upvotes, source_url)
                            VALUES (?, ?, ?, ?, ?)""",
                            (
                                post["id"],
                                post["subreddit"],
                                problem_text,
                                post["upvotes"],
                                post["url"],
                            ),
                        )
                        total_problems += 1

                # Only mark posts that Claude actually returned results for
                # plus all posts in batch (they were sent, Claude just found no problems)
                batch_ids = [p["id"] for p in batch_posts]
                conn.executemany(
                    "UPDATE raw_posts SET processed=1 WHERE id=?",
                    [(pid,) for pid in batch_ids],
                )
                conn.commit()

    logger.info(f"W2: extracted {total_problems} problems from {len(posts)} posts")


if __name__ == "__main__":
    run()
