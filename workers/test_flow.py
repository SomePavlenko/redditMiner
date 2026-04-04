"""
Тестовый флоу — минимальный прогон для отладки.

1. Хардкодит r/jobs в БД (без Claude)
2. W1a: 5 постов → trimmer → БД
3. W1b: 1 пост (топ) → trimmer комменты → БД
4. W2: 1 мини-батч с промптом → data/batches/test_batch_001.json
5. Итог + инструкция для Claude Code

Запуск: python3 -m workers.test_flow
Время: ~15 секунд
"""

import json
import time
import httpx
from datetime import datetime, timezone
from pathlib import Path

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from workers.helpers import load_config
from prompts import TEST_BATCH_PROMPT
from workers.trimmer import trim_posts, trim_comments
from workers.db import use_conn, init_db

HEADERS = {"User-Agent": "reddit-miner/1.0 personal research tool"}
TEST_SUB = "jobs"
MAX_POSTS = 5


def step1_add_subreddit():
    """Шаг 1: хардкодим тестовый сабреддит в БД."""
    print(f"\n{'='*50}")
    print(f"ШАГ 1: Добавляем r/{TEST_SUB} в БД")
    print(f"{'='*50}")

    init_db()
    config = load_config()

    with use_conn() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO subreddits (name, topic, weight, active)
            VALUES (?, ?, 5, 1)""",
            (TEST_SUB, config["topic"]),
        )
        conn.commit()
    print(f"  r/{TEST_SUB} добавлен")


def step2_fetch_posts():
    """Шаг 2: получаем посты, режем через trimmer."""
    config = load_config()
    # Для теста — низкий порог апвоутов
    test_config = {**config, "min_upvotes": 10}

    print(f"\n{'='*50}")
    print(f"ШАГ 2: Парсим r/{TEST_SUB} (топ {MAX_POSTS} постов)")
    print(f"{'='*50}")

    r = httpx.get(
        f"https://www.reddit.com/r/{TEST_SUB}/top.json",
        params={"t": "week", "limit": "25"},
        headers=HEADERS,
        timeout=15,
    )
    r.raise_for_status()

    raw_children = r.json()["data"]["children"]
    clean_posts = trim_posts(raw_children, test_config)[:MAX_POSTS]

    print(f"  Reddit вернул {len(raw_children)} постов → trimmer оставил {len(clean_posts)}:")
    for i, p in enumerate(clean_posts):
        print(f"  {i+1}. [{p['upvotes']}↑] {p['title'][:60]}")
        print(f"     body: {len(p['body'])} символов | flair: {p['flair'] or '—'}")

    # Сохраняем в БД
    saved = 0
    with use_conn() as conn:
        for post in clean_posts:
            try:
                conn.execute(
                    """INSERT OR IGNORE INTO raw_posts
                    (reddit_id, subreddit, topic, title, body, url, upvotes, parsed_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        post["reddit_id"], TEST_SUB, config["topic"], post["title"],
                        post["body"], post["url"], post["upvotes"],
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
                saved += 1
            except Exception as e:
                print(f"  Ошибка: {e}")
        conn.commit()

    print(f"  Сохранено: {saved}")
    return clean_posts


def step3_fetch_comments(posts):
    """Шаг 3: комменты к 1 топ посту через trimmer."""
    config = load_config()
    top_post = max(posts, key=lambda p: p["upvotes"])

    print(f"\n{'='*50}")
    print(f"ШАГ 3: Комменты к топ посту: {top_post['title'][:50]}")
    print(f"{'='*50}")

    time.sleep(1.1)
    r = httpx.get(
        f"https://www.reddit.com/r/{TEST_SUB}/comments/{top_post['reddit_id']}.json",
        params={"limit": "15", "sort": "top", "depth": "1"},
        headers=HEADERS,
        timeout=15,
    )
    r.raise_for_status()

    clean_comments = trim_comments(r.json(), config)

    print(f"  trimmer вернул {len(clean_comments)} комментариев:")
    for c in clean_comments[:5]:
        op_tag = " [OP]" if c["is_op"] else ""
        print(f"  [{c['ups']}↑]{op_tag} {c['text'][:70]}...")

    # Обновляем в БД
    with use_conn() as conn:
        conn.execute(
            "UPDATE raw_posts SET comments_json=?, comments_fetched=1 WHERE reddit_id=?",
            (json.dumps(clean_comments, ensure_ascii=False), top_post["reddit_id"]),
        )
        conn.commit()

    print(f"  Сохранены комментарии в БД")
    return clean_comments


def step4_prepare_batch():
    """Шаг 4: мини-батч для Claude Code."""
    config = load_config()
    body_max = config.get("body_max_chars", 300)
    comment_max = config.get("comment_max_chars", 200)

    print(f"\n{'='*50}")
    print(f"ШАГ 4: Готовим мини-батч для анализа")
    print(f"{'='*50}")

    with use_conn() as conn:
        posts = conn.execute(
            """SELECT id, subreddit, title, body, upvotes, url, comments_json
            FROM raw_posts WHERE processed=0
            ORDER BY upvotes DESC LIMIT 5"""
        ).fetchall()

    if not posts:
        print("  Нет необработанных постов!")
        return None

    batch_data = []
    for row in posts:
        comments = []
        if row["comments_json"]:
            try:
                comments = json.loads(row["comments_json"])[:5]
            except json.JSONDecodeError:
                pass

        batch_data.append({
            "post_db_id": row["id"],
            "subreddit": row["subreddit"],
            "title": row["title"],
            "body": (row["body"] or "")[:body_max],
            "upvotes": row["upvotes"],
            "url": row["url"],
            "top_comments": [
                {"text": c.get("text", "")[:comment_max], "ups": c.get("ups", 0)}
                for c in comments
            ],
        })

    batch_obj = {
        "_prompt": TEST_BATCH_PROMPT,
        "posts": batch_data,
    }

    root = os.path.join(os.path.dirname(__file__), "..")
    batches_dir = Path(os.path.join(root, "data", "batches"))
    batches_dir.mkdir(parents=True, exist_ok=True)
    for f in batches_dir.glob("test_batch_*.json"):
        f.unlink()

    filename = os.path.join(root, "data", "batches", "test_batch_001.json")
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(batch_obj, f, ensure_ascii=False, indent=2)

    size = os.path.getsize(filename)
    print(f"  Создан: {filename} ({len(batch_data)} постов, {size} байт)")
    return filename


def step5_summary(batch_file):
    """Шаг 5: итог."""
    print(f"\n{'='*50}")
    print(f"ИТОГ")
    print(f"{'='*50}")

    with use_conn() as conn:
        stats = {
            "сабреддитов": conn.execute("SELECT COUNT(*) FROM subreddits WHERE active=1").fetchone()[0],
            "постов": conn.execute("SELECT COUNT(*) FROM raw_posts").fetchone()[0],
            "необработанных": conn.execute("SELECT COUNT(*) FROM raw_posts WHERE processed=0").fetchone()[0],
            "с комментами": conn.execute("SELECT COUNT(*) FROM raw_posts WHERE comments_fetched=1").fetchone()[0],
            "болей": conn.execute("SELECT COUNT(*) FROM problems").fetchone()[0],
            "идей": conn.execute("SELECT COUNT(*) FROM ideas").fetchone()[0],
        }

    for k, v in stats.items():
        print(f"  {k}: {v}")

    if batch_file:
        print(f"\n  Батч: {batch_file}")
        print(f"\n  Следующий шаг — Claude Code:")
        print(f'  "Прочитай {batch_file}, выполни _prompt из файла"')


def run():
    print("\n🔧 ТЕСТОВЫЙ ФЛОУ\n")
    step1_add_subreddit()
    posts = step2_fetch_posts()
    if not posts:
        print("Не нашли постов")
        return
    step3_fetch_comments(posts)
    batch_file = step4_prepare_batch()
    step5_summary(batch_file)


if __name__ == "__main__":
    run()
