"""
S5 — Генерация идей через Claude API + скоринг + дедупликация.

Берёт топ кластеры болей, генерит SaaS-идеи, считает score, сохраняет в ideas.

python3 -m workers.s5_generate_ideas
"""

import json
from workers.helpers import load_config, load_env, setup_logger, claude_call, parse_json_response
from prompts import S5_GENERATE_IDEAS
from workers.db import use_conn


def is_duplicate(new_title, existing_titles, threshold):
    new_words = set(w for w in new_title.lower().split() if len(w) > 3)
    if not new_words:
        return False
    for existing in existing_titles:
        ex_words = set(w for w in existing.lower().split() if len(w) > 3)
        if not ex_words:
            continue
        overlap = len(new_words & ex_words) / len(new_words)
        if overlap >= threshold:
            return True
    return False



def run():
    config = load_config()
    load_env()
    logger = setup_logger("s5")
    topic = config["topic"]
    dedup_threshold = config.get("idea_dedup_similarity_threshold", 0.6)

    with use_conn() as conn:
        clusters = conn.execute(
            "SELECT * FROM pain_clusters WHERE topic=? ORDER BY pain_score DESC",
            (topic,),
        ).fetchall()

        existing_ideas = conn.execute(
            "SELECT title FROM ideas WHERE topic=? AND created_at >= datetime('now', '-30 days')",
            (topic,),
        ).fetchall()

    if not clusters:
        logger.info("S5: no clusters found")
        print("Нет кластеров. Сначала запусти S4.")
        return

    clusters_dict = {c["id"]: dict(c) for c in clusters}
    max_pain_score = max(c["pain_score"] for c in clusters) if clusters else 1

    clusters_for_prompt = [
        {
            "id": c["id"],
            "name": c["cluster_name"],
            "summary": c["summary"],
            "pain_score": c["pain_score"],
            "frequency": c["frequency"],
            "subreddit_spread": c["subreddit_spread"],
        }
        for c in clusters
    ]

    existing_titles = [r["title"] for r in existing_ideas]

    prompt = S5_GENERATE_IDEAS.format(
        topic=topic,
        clusters_json=json.dumps(clusters_for_prompt, ensure_ascii=False, indent=2),
        existing_titles=json.dumps(existing_titles, ensure_ascii=False),
    )

    logger.info(f"S5: sending {len(clusters)} clusters to Claude")
    raw = claude_call(config["claude_model_smart"], prompt, config, logger)

    try:
        ideas = parse_json_response(raw, logger)
    except json.JSONDecodeError as e:
        logger.error(f"S5: invalid JSON: {e}")
        return

    saved = 0
    duplicates = 0

    with use_conn() as conn:
        for idea in ideas:
            title = idea.get("title", "Untitled")

            dup_flag = 1 if is_duplicate(title, existing_titles, dedup_threshold) else 0
            if dup_flag:
                duplicates += 1

            solves = idea.get("solves_clusters", [])
            uniqueness = min(max(idea.get("uniqueness", 5), 1), 10)

            # Feasibility: use breakdown if available, otherwise use flat score
            fb = idea.get("feasibility_breakdown", {})
            if fb and isinstance(fb, dict):
                tech = min(max(fb.get("tech_complexity", 5), 1), 10)
                data = min(max(fb.get("data_availability", 5), 1), 10)
                deps = min(max(fb.get("third_party_deps", 5), 1), 10)
                legal = min(max(fb.get("legal_risk", 5), 1), 10)
                feasibility = round((tech + data + deps + legal) / 4, 1)
            else:
                feasibility = min(max(idea.get("feasibility", 5), 1), 10)

            solved_pain = [clusters_dict[cid]["pain_score"] for cid in solves if cid in clusters_dict]
            demand_score = (sum(solved_pain) / len(solved_pain)) / max_pain_score * 10 if solved_pain else 0
            breadth_score = min(len(solves) / max(len(clusters_dict) * 0.3, 1) * 10, 10)

            score = round(
                demand_score * 0.35 + breadth_score * 0.25 + feasibility * 0.20 + uniqueness * 0.20,
                2,
            )

            all_subs = set()
            for cid in solves:
                if cid in clusters_dict:
                    try:
                        all_subs.update(json.loads(clusters_dict[cid]["subreddits_json"]))
                    except (json.JSONDecodeError, TypeError):
                        pass

            conn.execute(
                """INSERT INTO ideas
                (topic, title, description, product_example, revenue_model,
                 score, demand_score, breadth_score, feasibility_score, uniqueness_score,
                 solves_clusters, subreddits, is_duplicate,
                 pain, solution, where_we_meet_user, monetization, monetization_type,
                 competition_level, competition_note, validation_step, feasibility_breakdown)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    topic, title,
                    idea.get("description", ""),
                    idea.get("product_example", ""),
                    idea.get("revenue_model", idea.get("monetization_type", "")),
                    score, round(demand_score, 2), round(breadth_score, 2),
                    feasibility, uniqueness,
                    json.dumps(solves), json.dumps(list(all_subs)),
                    dup_flag,
                    idea.get("pain", ""),
                    idea.get("solution", ""),
                    idea.get("where_we_meet_user", ""),
                    idea.get("monetization", ""),
                    idea.get("monetization_type", ""),
                    idea.get("competition_level", ""),
                    idea.get("competition_note", ""),
                    idea.get("validation_step", ""),
                    json.dumps(fb) if fb else None,
                ),
            )

            if not dup_flag:
                saved += 1
                for sub_name in all_subs:
                    conn.execute(
                        "UPDATE subreddits SET weight = weight + ?, total_ideas = total_ideas + 1 WHERE name=?",
                        (score * 0.1, sub_name),
                    )

            existing_titles.append(title)

        conn.commit()

    logger.info(f"S5: saved {saved} ideas, {duplicates} duplicates")
    print(f"\nS5: сохранено {saved} идей, {duplicates} дубликатов")

    with use_conn() as conn:
        top = conn.execute(
            """SELECT title, score, pain, competition_level, monetization, validation_step
            FROM ideas WHERE topic=? AND is_duplicate=0 ORDER BY score DESC LIMIT 10""",
            (topic,),
        ).fetchall()
    print("\nТоп идеи:")
    for i in top:
        comp = {"none": "нет рынка", "low": "слабая", "medium": "умеренная", "high": "высокая"}.get(i["competition_level"] or "", "")
        print(f"  [{i['score']:.1f}] {i['title']}")
        print(f"    Боль: {i['pain'] or ''}")
        print(f"    Конкуренция: {comp} | Монетизация: {i['monetization'] or ''}")
        print(f"    Первый шаг: {i['validation_step'] or ''}")
        print()


if __name__ == "__main__":
    run()
