"""
W0 — Topic Agent.
Находит сабреддиты по теме. Работает только через Claude Code (без API).

Режимы:
  python3 -m workers.s0_scout_subreddits --add jobs,resumes,careerguidance   # добавить вручную
  python3 -m workers.s0_scout_subreddits                                      # подготовить промпт для Claude Code
"""

import hashlib
import json
import os
import sys
from workers.helpers import load_config, setup_logger, ROOT
from workers.db import use_conn

TOPIC_HASH_FILE = os.path.join(ROOT, ".topic_hash")


def get_topic_hash(topic):
    return hashlib.md5(topic.encode()).hexdigest()


def topic_changed(topic):
    if os.path.exists(TOPIC_HASH_FILE):
        with open(TOPIC_HASH_FILE) as f:
            return f.read().strip() != get_topic_hash(topic)
    return True


def save_topic_hash(topic):
    with open(TOPIC_HASH_FILE, "w") as f:
        f.write(get_topic_hash(topic))


def add_subreddits(names, topic, logger):
    """Добавить сабреддиты вручную."""
    with use_conn() as conn:
        for name in names:
            name = name.strip().lower()
            if not name:
                continue
            conn.execute(
                """INSERT INTO subreddits (name, topic, weight, active)
                VALUES (?, ?, 5, 1)
                ON CONFLICT(name) DO UPDATE SET topic=?, active=1""",
                (name, topic, topic),
            )
            logger.info(f"W0: added r/{name}")
        conn.commit()

    save_topic_hash(topic)
    logger.info(f"W0: added {len(names)} subreddits for topic '{topic}'")


def prepare_prompt(topic, logger):
    """Готовит промпт-файл для поиска сабреддитов через Claude Code."""
    prompt_file = os.path.join(ROOT, "data", "find_subreddits_prompt.txt")
    os.makedirs(os.path.dirname(prompt_file), exist_ok=True)

    prompt = f"""Найди 15-20 сабреддитов Reddit где люди обсуждают проблемы по теме: "{topic}"

Мне нужны сабреддиты где пользователи ЖАЛУЮТСЯ, просят помощи, обсуждают что не работает.
Не нужны новостные или развлекательные сабреддиты.

Верни результат как команду для терминала:
python3 -m workers.s0_scout_subreddits --add sub1,sub2,sub3,...

Используй реальные названия сабреддитов без r/ префикса."""

    with open(prompt_file, "w") as f:
        f.write(prompt)

    logger.info(f"W0: prompt saved to {prompt_file}")
    print(f"Промпт готов: {prompt_file}")
    print(f"\nОткрой Claude Code и скажи:")
    print(f'  "Прочитай {prompt_file} и выполни задание"')
    print(f"\nИли добавь вручную:")
    print(f"  python3 -m workers.s0_scout_subreddits --add jobs,resumes,careerguidance")


def show_status(topic, logger):
    """Показать текущее состояние сабреддитов."""
    with use_conn() as conn:
        subs = conn.execute(
            "SELECT name, last_parsed_at, total_ideas, active FROM subreddits WHERE topic=? ORDER BY weight DESC",
            (topic,),
        ).fetchall()

    if not subs:
        print(f"Нет сабреддитов для темы '{topic}'")
        return False

    print(f"\nСабреддиты для темы '{topic}':")
    for s in subs:
        status = "✓" if s["active"] else "✗"
        parsed = s["last_parsed_at"] or "не парсился"
        print(f"  {status} r/{s['name']} | parsed: {parsed} | ideas: {s['total_ideas']}")
    return True


def run(force=False):
    config = load_config()
    topic = config["topic"]
    logger = setup_logger("s0")

    # Если --add, добавляем вручную
    if "--add" in sys.argv:
        idx = sys.argv.index("--add")
        if idx + 1 < len(sys.argv):
            names = sys.argv[idx + 1].split(",")
            add_subreddits(names, topic, logger)
            show_status(topic, logger)
            return
        else:
            print("Использование: python3 -m workers.s0_scout_subreddits --add jobs,resumes,careerguidance")
            return

    # Проверяем: есть ли уже сабреддиты для этой темы
    if not force and not topic_changed(topic):
        has_subs = show_status(topic, logger)
        if has_subs:
            logger.info(f"W0: topic '{topic}' unchanged, subreddits exist")
            return

    # Готовим промпт для Claude Code
    logger.info(f"W0: preparing prompt for topic '{topic}'")
    prepare_prompt(topic, logger)


if __name__ == "__main__":
    run(force="--force" in sys.argv)
