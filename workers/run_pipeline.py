"""
Полный пайплайн Reddit Miner.

Автоматические стадии (скрипты):
  S0 → S1a → S1b → S2 → [СТОП: Claude Code] → S3 → S4 → [СТОП: Claude Code] → S5

python3 -m workers.run_pipeline              # автоматическая часть (до первого СТОП)
python3 -m workers.run_pipeline --after-s2   # после Claude Code: S3 → S4 → промпт
python3 -m workers.run_pipeline --after-s4   # после Claude Code: S5
"""

import time
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from workers.helpers import setup_logger
from workers.db import init_db
from workers import s0_scout_subreddits, s1_fetch_reddit, s2_prepare_batches
from workers import s3_save_problems, s4_cluster_problems, s5_generate_ideas


def run_steps(steps, logger):
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
        time.sleep(1)


def run():
    logger = setup_logger("pipeline")
    init_db()
    args = sys.argv[1:]

    if "--after-s2" in args:
        # После того как Claude Code проанализировал батчи
        logger.info("=== Pipeline: after Claude analysis (S3 → S4) ===")
        run_steps([
            ("S3 Сохранение болей", lambda: s3_save_problems.run()),
            ("S4 Кластеризация (промпт)", lambda: s4_cluster_problems.run()),
        ], logger)
        print(f"\n{'=' * 50}")
        print("Кластеры подготовлены. Claude Code:")
        print(f'  "Прочитай data/cluster_prompt.json, выполни _prompt"')
        print(f"\nПосле Claude Code:")
        print(f"  python3 -m workers.run_pipeline --after-s4")

    elif "--after-s4" in args:
        # После того как Claude Code кластеризовал
        logger.info("=== Pipeline: after clustering (S4 save → S5) ===")
        run_steps([
            ("S4 Сохранение кластеров", lambda: s4_cluster_problems.save_clusters()),
            ("S5 Генерация идей (промпт)", lambda: s5_generate_ideas.run()),
        ], logger)
        print(f"\n{'=' * 50}")
        print("Промпт для идей готов. Claude Code:")
        print(f'  "Прочитай data/ideas_prompt.json, выполни _prompt"')
        print(f"\nПосле Claude Code:")
        print(f"  python3 -m workers.s5_generate_ideas --save")

    else:
        # Автоматическая часть: S0 → S1 → S2
        logger.info("=== Pipeline: auto stages (S0 → S1 → S2) ===")
        run_steps([
            ("S0 Разведка сабреддитов", lambda: s0_scout_subreddits.run()),
            ("S1 Парсинг Reddit", lambda: s1_fetch_reddit.run()),
            ("S2 Подготовка батчей", lambda: s2_prepare_batches.run()),
        ], logger)
        print(f"\n{'=' * 50}")
        print("Батчи готовы. Claude Code:")
        print(f'  "Прочитай файлы в data/batches/, выполни _prompt,')
        print(f'   сохрани результат в data/problems_raw.json"')
        print(f"\nПосле Claude Code:")
        print(f"  python3 -m workers.run_pipeline --after-s2")

    logger.info("=== Stage complete ===")


if __name__ == "__main__":
    run()
