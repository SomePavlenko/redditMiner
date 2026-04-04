"""
Полный пайплайн: разведка → парсинг → батчи → дайджест.
python3 -m workers.run_pipeline
"""

import time
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from workers.helpers import setup_logger
from workers.db import init_db
from workers import s0_scout_subreddits, s1_fetch_reddit, s2_prepare_batches, s3_prepare_digest


def run():
    logger = setup_logger("pipeline")
    logger.info("=== Pipeline start ===")

    init_db()

    steps = [
        ("S0 Разведка сабреддитов", lambda: s0_scout_subreddits.run()),
        ("S1 Парсинг Reddit", lambda: s1_fetch_reddit.run()),
        ("S2 Подготовка батчей", lambda: s2_prepare_batches.run()),
        ("S3 Подготовка дайджеста", lambda: s3_prepare_digest.run()),
    ]

    for name, fn in steps:
        logger.info(f"Starting {name}...")
        start = time.time()
        try:
            fn()
        except Exception as e:
            logger.error(f"{name} failed: {e}")
            raise
        elapsed = time.time() - start
        logger.info(f"{name} completed in {elapsed:.1f}s")
        time.sleep(2)

    logger.info("=== Pipeline complete ===")

    print(f"\n{'=' * 50}")
    print("ДАННЫЕ ГОТОВЫ. Следующий шаг — анализ через Claude Code:")
    print("=" * 50)
    print()
    print('  Скажи Claude:')
    print('  "Прочитай файлы в data/batches/, выполни _prompt из каждого файла"')
    print()


if __name__ == "__main__":
    run()
