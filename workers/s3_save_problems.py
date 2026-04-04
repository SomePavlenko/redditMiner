"""
S3 — Анализ болей через Claude API.

Берёт батчи из data/batches/, отправляет в Claude Haiku,
извлекает боли которые можно решить софтом, сохраняет в problems.

python3 -m workers.s3_save_problems
"""

import json
import os
from pathlib import Path
from workers.helpers import load_config, load_env, setup_logger, claude_call, parse_json_response, ROOT
from prompts import S3_ANALYZE_PAINS
from workers.db import use_conn

BATCHES_DIR = Path(os.path.join(ROOT, "data", "batches"))


def analyze_batch(batch_file, config, logger):
    with open(batch_file, encoding="utf-8") as f:
        batch_obj = json.load(f)

    posts = batch_obj.get("posts", [])
    if not posts:
        return []

    prompt = S3_ANALYZE_PAINS.format(
        topic=config["topic"],
        posts_json=json.dumps(posts, ensure_ascii=False),
    )
    raw = claude_call(config["claude_model_fast"], prompt, config, logger)
    return parse_json_response(raw, logger)


def run():
    config = load_config()
    load_env()
    logger = setup_logger("s3")
    topic = config["topic"]

    batch_files = sorted(BATCHES_DIR.glob("batch_*.json"))
    if not batch_files:
        logger.info("S3: no batch files found")
        print("Нет батчей. Сначала запусти S2.")
        return

    total_problems = 0
    total_posts = 0

    for bf in batch_files:
        try:
            results = analyze_batch(bf, config, logger)
        except json.JSONDecodeError as e:
            logger.error(f"S3: invalid JSON for {bf.name}: {e}")
            continue
        except Exception as e:
            logger.error(f"S3: {bf.name} failed: {e}")
            continue

        with use_conn() as conn:
            for item in results:
                post_id = item.get("post_db_id")
                if not post_id:
                    continue

                row = conn.execute("SELECT upvotes, subreddit, url FROM raw_posts WHERE id=?", (post_id,)).fetchone()
                if not row:
                    continue
                upvotes = row["upvotes"]
                subreddit = item.get("subreddit", row["subreddit"])
                url = item.get("url", row["url"] or "")

                for problem_text in item.get("problems", []):
                    if not problem_text or len(problem_text.strip()) < 5:
                        continue
                    conn.execute(
                        """INSERT INTO problems (raw_post_id, subreddit, topic, problem, upvotes, source_url)
                        VALUES (?, ?, ?, ?, ?, ?)""",
                        (post_id, subreddit, topic, problem_text.strip(), upvotes, url),
                    )
                    total_problems += 1

                conn.execute("UPDATE raw_posts SET processed=1 WHERE id=?", (post_id,))
                total_posts += 1

            conn.commit()

        logger.info(f"S3: processed {bf.name}")

    logger.info(f"S3: saved {total_problems} problems from {total_posts} posts")
    print(f"S3: сохранено {total_problems} болей из {total_posts} постов")


if __name__ == "__main__":
    run()
