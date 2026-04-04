"""
S2 — Подготовка батчей для анализа.
Берёт топ-150 необработанных постов по апвоутам, формирует батчи по 40.

python3 -m workers.s2_prepare_batches
"""

import json
import os
from pathlib import Path
from workers.helpers import load_config, setup_logger, ROOT
from workers.db import use_conn

MAX_POSTS_FOR_ANALYSIS = 150
BATCH_SIZE = 40


def prepare_batches():
    config = load_config()
    logger = setup_logger("s2")
    topic = config["topic"]

    body_max = config.get("body_max_chars", 300)
    comment_max = config.get("comment_max_chars", 200)
    comments_top = config.get("comments_top_n", 10)

    with use_conn() as conn:
        posts = conn.execute(
            """SELECT id, reddit_id, subreddit, title, body, upvotes, url, comments_json
            FROM raw_posts
            WHERE processed = 0 AND (topic=? OR topic='')
            ORDER BY upvotes DESC
            LIMIT ?""",
            (topic, MAX_POSTS_FOR_ANALYSIS),
        ).fetchall()

    if not posts:
        logger.info("S2: no unprocessed posts")
        print("Нет необработанных постов")
        return []

    batches_dir = Path(os.path.join(ROOT, "data", "batches"))
    batches_dir.mkdir(parents=True, exist_ok=True)

    for f in batches_dir.glob("batch_*.json"):
        f.unlink()

    batch_files = []
    for i in range(0, len(posts), BATCH_SIZE):
        batch = posts[i : i + BATCH_SIZE]
        batch_data = []

        for row in batch:
            comments = []
            if row["comments_json"]:
                try:
                    raw_comments = json.loads(row["comments_json"])
                    comments = [
                        {"text": c.get("text", "")[:comment_max], "ups": c.get("ups", 0)}
                        for c in sorted(raw_comments, key=lambda x: x.get("ups", 0), reverse=True)[:comments_top]
                    ]
                except json.JSONDecodeError:
                    pass

            batch_data.append({
                "post_db_id": row["id"],
                "subreddit": row["subreddit"],
                "title": row["title"],
                "body": (row["body"] or "")[:body_max],
                "upvotes": row["upvotes"],
                "url": row["url"],
                "top_comments": comments,
            })

        filename = os.path.join(ROOT, "data", "batches", f"batch_{i // BATCH_SIZE + 1:03d}.json")
        with open(filename, "w", encoding="utf-8") as f:
            json.dump({"posts": batch_data}, f, ensure_ascii=False, indent=2)

        batch_files.append(filename)
        print(f"  Создан {os.path.basename(filename)} ({len(batch_data)} постов)")

    logger.info(f"S2: prepared {len(batch_files)} batches from {len(posts)} posts (top {MAX_POSTS_FOR_ANALYSIS})")
    print(f"\nГотово: {len(batch_files)} батчей из топ-{len(posts)} постов")

    return batch_files


def run():
    prepare_batches()


if __name__ == "__main__":
    run()
