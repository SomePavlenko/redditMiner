"""
S4 — Кластеризация болей через Claude API.

Собирает все боли за 7 дней, отправляет в Claude Haiku для кластеризации,
считает pain_score, сохраняет в таблицу pain_clusters.

python3 -m workers.s4_cluster_problems
"""

import json
import math
from workers.helpers import load_config, load_env, setup_logger, claude_call, parse_json_response
from workers.db import use_conn


def run():
    config = load_config()
    load_env()
    logger = setup_logger("s4")
    topic = config["topic"]

    with use_conn() as conn:
        problems = conn.execute(
            """SELECT id, problem, subreddit, upvotes
            FROM problems
            WHERE parsed_at >= datetime('now', '-7 days')
            ORDER BY upvotes DESC"""
        ).fetchall()

    if not problems:
        logger.info("S4: no problems to cluster")
        print("Нет болей для кластеризации")
        return

    # Ограничиваем до 150 топ болей чтобы влезть в контекст
    problems = problems[:150]

    problems_list = [
        {"id": p["id"], "problem": p["problem"], "subreddit": p["subreddit"], "upvotes": p["upvotes"]}
        for p in problems
    ]

    prompt = f"""You are a user pain analyst. Topic: "{topic}"

Below are {len(problems_list)} user pain points from Reddit.
Many describe the same problem in different words.

TASK:
1. Group similar pains into clusters (5-20 clusters)
2. Give each a short name (3-5 words, in Russian)
3. Write summary — essence of the pain in 1-2 sentences (in Russian)
4. Focus on pains that could be solved with software/SaaS

Return ONLY JSON array, no markdown:
[{{"cluster_name": "Название кластера", "summary": "Суть проблемы", "problem_ids": [1, 5, 12]}}]

RULES:
- One problem can only be in one cluster
- No "Other" or "Miscellaneous" clusters
- Names must be specific: "ATS rejects resumes" not "Resume problems"
- cluster_name and summary MUST be in Russian

Pains:
{json.dumps(problems_list, ensure_ascii=False)}"""

    logger.info(f"S4: sending {len(problems_list)} problems to Claude for clustering")
    raw = claude_call(config["claude_model_fast"], prompt, config, logger)

    try:
        clusters = parse_json_response(raw, logger)
    except json.JSONDecodeError as e:
        logger.error(f"S4: Claude returned invalid JSON: {e}")
        return

    # Сохраняем кластеры с метриками
    with use_conn() as conn:
        conn.execute("DELETE FROM pain_clusters WHERE topic=?", (topic,))

        for cluster in clusters:
            problem_ids = cluster.get("problem_ids", [])

            # Get actual subreddits from problems table
            if problem_ids:
                placeholders = ",".join("?" * len(problem_ids))
                sub_rows = conn.execute(
                    f"SELECT DISTINCT subreddit FROM problems WHERE id IN ({placeholders})",
                    problem_ids,
                ).fetchall()
                subreddits = [r["subreddit"] for r in sub_rows]
            else:
                subreddits = []

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

            for pid in problem_ids:
                conn.execute("UPDATE problems SET cluster_id=? WHERE id=?", (cluster_id, pid))

        conn.commit()

    logger.info(f"S4: saved {len(clusters)} clusters")
    print(f"S4: сохранено {len(clusters)} кластеров")

    # Топ кластеры
    with use_conn() as conn:
        top = conn.execute(
            "SELECT cluster_name, pain_score, frequency, subreddit_spread FROM pain_clusters WHERE topic=? ORDER BY pain_score DESC LIMIT 10",
            (topic,),
        ).fetchall()
    print("\nТоп кластеры:")
    for c in top:
        print(f"  [{c['pain_score']:.1f}] {c['cluster_name']} (×{c['frequency']}, {c['subreddit_spread']} сабов)")


if __name__ == "__main__":
    run()
