import json
import asyncio
from workers.helpers import load_config, load_env, setup_logger, claude_call
from workers.db import get_conn


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


async def process_batch(batch_posts, config, logger):
    prompt = build_batch_prompt(batch_posts)
    raw = claude_call("claude-haiku-4-5-20250901", prompt, config, logger)
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
    return json.loads(raw)


def run():
    config = load_config()
    load_env()
    logger = setup_logger("w2")
    conn = get_conn()

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

    for chunk_start in range(0, len(batches), 5):
        chunk = batches[chunk_start : chunk_start + 5]

        async def _run_chunk():
            tasks = [process_batch(b, config, logger) for b in chunk]
            return await asyncio.gather(*tasks, return_exceptions=True)

        results = asyncio.run(_run_chunk())

        for batch_posts, result in zip(chunk, results):
            if isinstance(result, Exception):
                logger.error(f"W2: batch failed: {result}")
                continue

            post_map = {p["id"]: p for p in batch_posts}
            for item in result:
                post = post_map.get(item["post_id"])
                if not post:
                    continue
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

            batch_ids = [p["id"] for p in batch_posts]
            conn.executemany(
                "UPDATE raw_posts SET processed=1 WHERE id=?",
                [(pid,) for pid in batch_ids],
            )
            conn.commit()

    conn.close()
    logger.info(f"W2: extracted {total_problems} problems from {len(posts)} posts")


if __name__ == "__main__":
    run()
