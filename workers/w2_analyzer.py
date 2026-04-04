import json
from pathlib import Path
from workers.helpers import load_config, setup_logger
from workers.db import use_conn


def prepare_batches(batch_size=None):
    config = load_config()
    logger = setup_logger("w2")
    if batch_size is None:
        batch_size = config["claude_batch_size"]

    with use_conn() as conn:
        posts = conn.execute(
            """SELECT id, reddit_id, subreddit, title, body, upvotes, url, comments_json
            FROM raw_posts
            WHERE processed = 0
            ORDER BY upvotes DESC"""
        ).fetchall()

    if not posts:
        logger.info("W2: no unprocessed posts")
        print("Нет необработанных постов")
        return []

    batches_dir = Path("data/batches")
    batches_dir.mkdir(parents=True, exist_ok=True)

    # Clean old batches
    for f in batches_dir.glob("batch_*.json"):
        f.unlink()

    batch_files = []
    for i in range(0, len(posts), batch_size):
        batch = posts[i : i + batch_size]
        batch_data = []

        for row in batch:
            comments = []
            if row["comments_json"]:
                try:
                    comments = json.loads(row["comments_json"])
                except json.JSONDecodeError:
                    pass

            batch_data.append({
                "post_db_id": row["id"],
                "subreddit": row["subreddit"],
                "title": row["title"],
                "body": (row["body"] or "")[:400],
                "upvotes": row["upvotes"],
                "url": row["url"],
                "top_comments": sorted(
                    [{"text": c.get("text", "")[:250], "ups": c.get("ups", 0)} for c in comments],
                    key=lambda x: x["ups"],
                    reverse=True,
                )[:5],
            })

        filename = f"data/batches/batch_{i // batch_size + 1:03d}.json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(batch_data, f, ensure_ascii=False, indent=2)

        batch_files.append(filename)
        print(f"Создан {filename} ({len(batch_data)} постов)")

    logger.info(f"W2: prepared {len(batch_files)} batches from {len(posts)} posts")
    print(f"\nГотово: {len(batch_files)} батчей в data/batches/")
    print(f"\nТеперь запусти Claude Code:")
    print(f'  claude')
    print(f'  > "Проанализируй батчи в data/batches/ и извлеки боли пользователей"')

    return batch_files


def mark_as_processed(post_ids):
    """Пометить посты как обработанные после анализа через Claude Code."""
    with use_conn() as conn:
        conn.executemany(
            "UPDATE raw_posts SET processed=1 WHERE id=?",
            [(pid,) for pid in post_ids],
        )
        conn.commit()
    print(f"Помечено {len(post_ids)} постов как обработанные")


def run():
    prepare_batches()


if __name__ == "__main__":
    run()
