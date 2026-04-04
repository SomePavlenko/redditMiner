"""
W2 — Подготовка батчей для анализа через Claude Code.
Берёт необработанные посты, обрезает, формирует JSON-файлы с промптом внутри.

python3 -m workers.s2_prepare_batches
"""

import json
import os
from pathlib import Path
from workers.helpers import load_config, setup_logger, ROOT
from workers.db import use_conn


def prepare_batches(batch_size=None):
    config = load_config()
    logger = setup_logger("s2")
    if batch_size is None:
        batch_size = config["claude_batch_size"]

    body_max = config.get("body_max_chars", 300)
    comment_max = config.get("comment_max_chars", 200)
    comments_top = config.get("comments_top_n", 10)

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

    batches_dir = Path(os.path.join(ROOT, "data", "batches"))
    batches_dir.mkdir(parents=True, exist_ok=True)

    # Чистим старые батчи
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
                    raw_comments = json.loads(row["comments_json"])
                    comments = [
                        {
                            "text": c.get("text", "")[:comment_max],
                            "ups": c.get("ups", 0),
                        }
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

        batch_obj = {
            "_prompt": (
                "Проанализируй посты ниже. Для каждого поста найди КОНКРЕТНЫЕ боли пользователей — "
                "что не работает, что раздражает, что хотят улучшить. "
                "Игнорируй общие жалобы без конкретики и позитивные посты.\n\n"
                "Результат запиши в БД data/miner.db, таблица problems:\n"
                "  INSERT INTO problems (raw_post_id, subreddit, problem, upvotes, source_url)\n"
                "  VALUES (post_db_id, subreddit, 'текст боли', upvotes, url)\n\n"
                "После записи пометь посты обработанными:\n"
                "  UPDATE raw_posts SET processed=1 WHERE id IN (все post_db_id из этого батча)"
            ),
            "posts": batch_data,
        }

        filename = os.path.join(ROOT, "data", "batches", f"batch_{i // batch_size + 1:03d}.json")
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(batch_obj, f, ensure_ascii=False, indent=2)

        batch_files.append(filename)
        print(f"  Создан {filename} ({len(batch_data)} постов)")

    logger.info(f"W2: prepared {len(batch_files)} batches from {len(posts)} posts")
    print(f"\nГотово: {len(batch_files)} батчей в data/batches/")
    print(f"\nОткрой Claude Code и скажи:")
    print(f'  "Прочитай файлы в data/batches/, выполни _prompt из каждого файла"')

    return batch_files


def run():
    prepare_batches()


if __name__ == "__main__":
    run()
