import time
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from workers.helpers import setup_logger
from workers.db import init_db
from workers import w0_topic, w1_parser, w2_analyzer, w3_digest


def run():
    logger = setup_logger("run_all")
    logger.info("=== Cold start: running full pipeline ===")

    init_db()

    steps = [
        ("W0 Topic Scout", lambda: w0_topic.run(force=True)),
        ("W1 Reddit Parser", lambda: w1_parser.run()),
        ("W2 Подготовка батчей", lambda: w2_analyzer.run()),
        ("W3 Подготовка дайджеста", lambda: w3_digest.run()),
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
    print('  "Прочитай data/batches/, извлеки боли, запиши в БД,')
    print('   потом прочитай data/digest_context.json,')
    print('   сгенерируй топ идеи и запиши в БД таблица ideas"')
    print()


if __name__ == "__main__":
    run()
