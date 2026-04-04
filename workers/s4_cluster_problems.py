"""
S4 — Кластеризация болей.

Флоу:
  1. Скрипт собирает все problems → готовит data/cluster_prompt.json
  2. Claude Code кластеризует + даёт названия → сохраняет data/clusters_raw.json
  3. python3 -m workers.s4_cluster_problems --save  → читает clusters_raw.json → БД

Формат data/clusters_raw.json (Claude Code создаёт):
[
  {
    "cluster_name": "Короткое название кластера",
    "summary": "Суть боли в 1-2 предложения",
    "problem_ids": [1, 5, 12, 34],
    "subreddits": ["jobs", "careerguidance"]
  }
]

python3 -m workers.s4_cluster_problems           # подготовить промпт
python3 -m workers.s4_cluster_problems --save     # сохранить результат Claude
"""

import json
import math
import os
import sys
from workers.helpers import load_config, setup_logger, ROOT
from workers.db import use_conn

CLUSTER_PROMPT_FILE = os.path.join(ROOT, "data", "cluster_prompt.json")
CLUSTERS_RAW_FILE = os.path.join(ROOT, "data", "clusters_raw.json")


def prepare_prompt():
    """Готовит данные для кластеризации через Claude Code."""
    config = load_config()
    logger = setup_logger("s4")
    topic = config["topic"]

    with use_conn() as conn:
        problems = conn.execute(
            """SELECT id, problem, subreddit, upvotes, source_url
            FROM problems
            WHERE parsed_at >= datetime('now', '-7 days')
            ORDER BY upvotes DESC"""
        ).fetchall()

    if not problems:
        print("Нет болей для кластеризации")
        return

    problems_list = [
        {
            "id": p["id"],
            "problem": p["problem"],
            "subreddit": p["subreddit"],
            "upvotes": p["upvotes"],
        }
        for p in problems
    ]

    prompt_data = {
        "_prompt": f"""Ты аналитик пользовательских проблем. Тема: "{topic}"

Ниже список болей пользователей Reddit ({len(problems_list)} штук).
Многие из них описывают одну и ту же проблему разными словами.

ЗАДАНИЕ:
1. Сгруппируй похожие боли в кластеры (5-20 кластеров)
2. Дай каждому кластеру короткое название (3-5 слов)
3. Напиши summary — суть боли в 1-2 предложения
4. Укажи ID проблем которые входят в кластер
5. Укажи из каких сабреддитов проблемы

Верни JSON и сохрани в data/clusters_raw.json:
[
  {{
    "cluster_name": "Название кластера",
    "summary": "Суть проблемы",
    "problem_ids": [1, 5, 12],
    "subreddits": ["jobs", "careerguidance"]
  }}
]

ПРАВИЛА:
- Одна проблема может быть только в одном кластере
- Не создавай кластер "Прочее" — лучше мелкие конкретные кластеры
- Названия должны быть конкретными: "ATS отклоняет резюме" а не "Проблемы с резюме"
- Кластеры с 1 проблемой — ок, если боль уникальная и важная""",
        "problems": problems_list,
    }

    with open(CLUSTER_PROMPT_FILE, "w", encoding="utf-8") as f:
        json.dump(prompt_data, f, ensure_ascii=False, indent=2)

    logger.info(f"S4: prepared {len(problems_list)} problems for clustering")
    print(f"Промпт готов: {CLUSTER_PROMPT_FILE} ({len(problems_list)} болей)")
    print(f'\nОткрой Claude Code:')
    print(f'  "Прочитай {CLUSTER_PROMPT_FILE}, выполни _prompt"')


def save_clusters():
    """Читает результат Claude Code и сохраняет кластеры в БД."""
    config = load_config()
    logger = setup_logger("s4")
    topic = config["topic"]

    if not os.path.exists(CLUSTERS_RAW_FILE):
        print(f"Файл {CLUSTERS_RAW_FILE} не найден. Сначала запусти Claude Code.")
        return

    with open(CLUSTERS_RAW_FILE, encoding="utf-8") as f:
        clusters = json.load(f)

    with use_conn() as conn:
        # Очищаем старые кластеры по теме
        conn.execute("DELETE FROM pain_clusters WHERE topic=?", (topic,))

        for cluster in clusters:
            problem_ids = cluster.get("problem_ids", [])
            subreddits = cluster.get("subreddits", [])

            # Считаем метрики из реальных данных
            frequency = len(problem_ids)
            subreddit_spread = len(set(subreddits))

            total_upvotes = 0
            if problem_ids:
                placeholders = ",".join("?" * len(problem_ids))
                rows = conn.execute(
                    f"SELECT upvotes FROM problems WHERE id IN ({placeholders})",
                    problem_ids,
                ).fetchall()
                total_upvotes = sum(r["upvotes"] for r in rows)

            avg_upvotes = total_upvotes / frequency if frequency > 0 else 0

            # pain_score: frequency×2 + subreddit_spread×3 + log(total_upvotes+1)
            pain_score = (frequency * 2) + (subreddit_spread * 3) + math.log(total_upvotes + 1)

            cluster_id = conn.execute(
                """INSERT INTO pain_clusters
                (topic, cluster_name, summary, problems_json, frequency,
                 total_upvotes, avg_upvotes, subreddit_spread, subreddits_json, pain_score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    topic,
                    cluster.get("cluster_name", ""),
                    cluster.get("summary", ""),
                    json.dumps(problem_ids),
                    frequency,
                    total_upvotes,
                    round(avg_upvotes, 1),
                    subreddit_spread,
                    json.dumps(subreddits),
                    round(pain_score, 2),
                ),
            ).lastrowid

            # Обновляем cluster_id в problems
            for pid in problem_ids:
                conn.execute("UPDATE problems SET cluster_id=? WHERE id=?", (cluster_id, pid))

        conn.commit()

    logger.info(f"S4: saved {len(clusters)} clusters")
    print(f"Сохранено: {len(clusters)} кластеров")

    # Показываем топ
    with use_conn() as conn:
        top = conn.execute(
            "SELECT cluster_name, pain_score, frequency, subreddit_spread FROM pain_clusters WHERE topic=? ORDER BY pain_score DESC LIMIT 10",
            (topic,),
        ).fetchall()
    print("\nТоп кластеры:")
    for c in top:
        print(f"  [{c['pain_score']:.1f}] {c['cluster_name']} (×{c['frequency']}, {c['subreddit_spread']} сабов)")

    os.rename(CLUSTERS_RAW_FILE, CLUSTERS_RAW_FILE + ".done")


def run():
    if "--save" in sys.argv:
        save_clusters()
    else:
        prepare_prompt()


if __name__ == "__main__":
    run()
