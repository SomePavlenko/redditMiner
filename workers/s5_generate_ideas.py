"""
S5 — Генерация идей через Claude API + скоринг + дедупликация.

Берёт топ кластеры болей, генерит SaaS-идеи, считает score, сохраняет в ideas.

python3 -m workers.s5_generate_ideas
"""

import json
import math
from workers.helpers import load_config, load_env, setup_logger, claude_call, parse_json_response
from prompts import S5_GENERATE_IDEAS
from workers.db import use_conn


def clamp(v, lo=1, hi=10):
    return min(max(v, lo), hi)


def compute_score(idea, clusters_dict, max_pain_score, config):
    weights = config.get("scoring_weights", {
        "demand": 0.30, "feasibility": 0.25, "reachability": 0.15,
        "willingness_to_pay": 0.15, "uniqueness": 0.10, "retention": 0.05,
    })
    market_mults = config.get("scoring_market_multipliers", {
        "saas_subscription": 1.3, "freemium": 1.1, "b2b_license": 1.2, "one_time": 0.8,
    })
    speed_threshold = config.get("scoring_speed_bonus_threshold", 8)

    solves = idea.get("solves_clusters", [])
    uniqueness = clamp(idea.get("uniqueness", 5))
    reachability = clamp(idea.get("reachability", 5))
    willingness = clamp(idea.get("willingness_to_pay", 5))
    retention = clamp(idea.get("retention_potential", 5))

    # Feasibility composite with min-penalty
    fb = idea.get("feasibility_breakdown", {})
    if fb and isinstance(fb, dict):
        tech = clamp(fb.get("tech_complexity", 5))
        data_av = clamp(fb.get("data_availability", 5))
        deps = clamp(fb.get("third_party_deps", 5))
        legal = clamp(fb.get("legal_risk", 5))
        components = [tech, data_av, deps, legal]
        min_c = min(components)
        avg_c = sum(components) / 4
        feasibility = min_c * 0.6 + avg_c * 0.4 if min_c < 4 else avg_c
    else:
        feasibility = clamp(idea.get("feasibility", 5))

    # Demand from cluster data
    solved_pain = [clusters_dict[cid]["pain_score"] for cid in solves if cid in clusters_dict]
    demand = (sum(solved_pain) / len(solved_pain)) / max_pain_score * 10 if solved_pain else 0

    # Breadth (kept for DB, not in main score)
    breadth = min(len(solves) / max(len(clusters_dict) * 0.3, 1) * 10, 10) if clusters_dict else 0

    competition = idea.get("competition_level", "")
    monetization_type = idea.get("monetization_type", "")

    # Level 1: Kill conditions
    blocked = False
    block_reason = None
    if fb and isinstance(fb, dict):
        if clamp(fb.get("legal_risk", 5)) <= 2:
            blocked, block_reason = True, "legal_risk"
        if clamp(fb.get("data_availability", 5)) <= 2:
            blocked, block_reason = True, "data_unavailable"
    if competition == "none":
        blocked, block_reason = True, "no_market"
    if feasibility <= 3:
        blocked, block_reason = True, "not_buildable"

    if blocked:
        return {
            "score": round(min(3.0, demand * 0.3), 2),
            "demand_score": round(demand, 2),
            "breadth_score": round(breadth, 2),
            "feasibility_score": round(feasibility, 1),
            "uniqueness_score": uniqueness,
            "reachability": reachability,
            "willingness_to_pay": willingness,
            "retention_potential": retention,
        }

    # Level 2: Geometric weighted mean
    factors = {
        "demand":             (max(demand, 0.1),      weights.get("demand", 0.30)),
        "feasibility":        (max(feasibility, 0.1),  weights.get("feasibility", 0.25)),
        "reachability":       (max(reachability, 0.1), weights.get("reachability", 0.15)),
        "willingness_to_pay": (max(willingness, 0.1),  weights.get("willingness_to_pay", 0.15)),
        "uniqueness":         (max(uniqueness, 0.1),   weights.get("uniqueness", 0.10)),
        "retention":          (max(retention, 0.1),    weights.get("retention", 0.05)),
    }

    log_sum = sum(w * math.log(v) for v, w in factors.values())
    total_w = sum(w for _, w in factors.values())
    iqs = math.exp(log_sum / total_w)

    # Level 3: Business multiplier
    mm = market_mults.get(monetization_type, 1.0)
    speed = 1.1 if feasibility >= speed_threshold else 1.0
    score = round(min(10, iqs * mm * speed), 2)

    return {
        "score": score,
        "demand_score": round(demand, 2),
        "breadth_score": round(breadth, 2),
        "feasibility_score": round(feasibility, 1),
        "uniqueness_score": uniqueness,
        "reachability": reachability,
        "willingness_to_pay": willingness,
        "retention_potential": retention,
    }


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
            fb = idea.get("feasibility_breakdown", {})

            s = compute_score(idea, clusters_dict, max_pain_score, config)
            score = s["score"]
            demand_score = s["demand_score"]
            breadth_score = s["breadth_score"]
            feasibility = s["feasibility_score"]
            uniqueness = s["uniqueness_score"]
            reachability = s["reachability"]
            willingness_to_pay = s["willingness_to_pay"]
            retention_potential = s["retention_potential"]

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
                 reachability, willingness_to_pay, retention_potential,
                 solves_clusters, subreddits, is_duplicate,
                 pain, solution, where_we_meet_user, monetization, monetization_type,
                 competition_level, competition_note, validation_step, feasibility_breakdown)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    topic, title,
                    idea.get("description", ""),
                    idea.get("product_example", ""),
                    idea.get("revenue_model", idea.get("monetization_type", "")),
                    score, demand_score, breadth_score,
                    feasibility, uniqueness,
                    reachability, willingness_to_pay, retention_potential,
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
