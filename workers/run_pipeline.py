"""
Полный автоматический пайплайн Reddit Miner.
Все стадии запускаются последовательно, без ручного вмешательства.

python3 -m workers.run_pipeline
"""

import time
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from workers.helpers import setup_logger
from workers.db import init_db
from workers import s0_scout_subreddits, s1_fetch_reddit, s2_prepare_batches
from workers import s3_save_problems, s4_cluster_problems, s5_generate_ideas


def run():
    logger = setup_logger("pipeline")
    init_db()

    logger.info("=== Pipeline start ===")

    steps = [
        ("S0 Разведка сабреддитов", lambda: s0_scout_subreddits.run()),
        ("S1 Парсинг Reddit", lambda: s1_fetch_reddit.run()),
        ("S2 Подготовка батчей", lambda: s2_prepare_batches.run()),
        ("S3 Анализ болей (Claude Haiku)", lambda: s3_save_problems.run()),
        ("S4 Кластеризация (Claude Haiku)", lambda: s4_cluster_problems.run()),
        ("S5 Генерация идей (Claude Sonnet)", lambda: s5_generate_ideas.run()),
    ]

    for name, fn in steps:
        logger.info(f"Starting {name}...")
        start = time.time()
        try:
            fn()
        except Exception as e:
            logger.error(f"{name} failed: {e}")
            print(f"\n❌ {name} упал: {e}")
            return
        elapsed = time.time() - start
        logger.info(f"{name} completed in {elapsed:.1f}s")
        print(f"✓ {name} ({elapsed:.1f}s)")
        time.sleep(1)

    logger.info("=== Pipeline complete ===")
    print(f"\n{'=' * 50}")
    print("Пайплайн завершён. Результаты:")
    print("=" * 50)

    from workers.db import use_conn
    with use_conn() as conn:
        stats = {
            "постов": conn.execute("SELECT COUNT(*) FROM raw_posts").fetchone()[0],
            "болей": conn.execute("SELECT COUNT(*) FROM problems").fetchone()[0],
            "кластеров": conn.execute("SELECT COUNT(*) FROM pain_clusters").fetchone()[0],
            "идей": conn.execute("SELECT COUNT(*) FROM ideas WHERE is_duplicate=0").fetchone()[0],
        }
    for k, v in stats.items():
        print(f"  {k}: {v}")

    print(f"\nСмотреть: sqlite3 data/miner.db \"SELECT title, score FROM ideas ORDER BY score DESC LIMIT 10;\"")
    print(f"Или: http://localhost:3000 (если API и фронт запущены)")


if __name__ == "__main__":
    run()
