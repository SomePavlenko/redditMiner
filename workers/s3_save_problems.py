"""
S3 — Сохранение болей из результата Claude Code в БД.

Флоу:
  1. Claude Code анализирует батчи → сохраняет data/problems_raw.json
  2. Этот скрипт читает файл → валидирует → INSERT в problems → ставит processed=1

Формат data/problems_raw.json:
[
  {
    "post_db_id": 123,
    "subreddit": "jobs",
    "problems": ["боль 1", "боль 2"],
    "url": "https://reddit.com/..."
  }
]

python3 -m workers.s3_save_problems
"""

import json
import os
from pathlib import Path
from workers.helpers import load_config, setup_logger, ROOT
from workers.db import use_conn

PROBLEMS_FILE = os.path.join(ROOT, "data", "problems_raw.json")


def run():
    logger = setup_logger("s3")

    if not os.path.exists(PROBLEMS_FILE):
        print(f"Файл {PROBLEMS_FILE} не найден.")
        print("Сначала запусти Claude Code для анализа батчей.")
        print('Скажи: "Прочитай файлы в data/batches/, выполни _prompt, сохрани результат в data/problems_raw.json"')
        return

    with open(PROBLEMS_FILE, encoding="utf-8") as f:
        data = json.load(f)

    if not data:
        print("Файл пустой")
        return

    total_problems = 0
    post_ids = []

    with use_conn() as conn:
        for item in data:
            post_id = item.get("post_db_id")
            subreddit = item.get("subreddit", "")
            url = item.get("url", "")
            problems = item.get("problems", [])

            if post_id:
                post_ids.append(post_id)

                # Получаем upvotes из raw_posts
                row = conn.execute("SELECT upvotes FROM raw_posts WHERE id=?", (post_id,)).fetchone()
                upvotes = row["upvotes"] if row else 0

                for problem_text in problems:
                    if not problem_text or len(problem_text.strip()) < 5:
                        continue
                    conn.execute(
                        """INSERT INTO problems (raw_post_id, subreddit, problem, upvotes, source_url)
                        VALUES (?, ?, ?, ?, ?)""",
                        (post_id, subreddit, problem_text.strip(), upvotes, url),
                    )
                    total_problems += 1

        # Помечаем посты обработанными
        if post_ids:
            conn.executemany(
                "UPDATE raw_posts SET processed=1 WHERE id=?",
                [(pid,) for pid in post_ids],
            )
        conn.commit()

    logger.info(f"S3: saved {total_problems} problems from {len(post_ids)} posts")
    print(f"Сохранено: {total_problems} болей из {len(post_ids)} постов")

    # Удаляем обработанный файл
    os.rename(PROBLEMS_FILE, PROBLEMS_FILE + ".done")
    print(f"Файл перемещён в {PROBLEMS_FILE}.done")


if __name__ == "__main__":
    run()
