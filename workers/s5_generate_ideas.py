"""
S5 — Генерация идей через Claude API + скоринг + дедупликация.

Берёт топ кластеры болей, генерит SaaS-идеи, считает score, сохраняет в ideas.

python3 -m workers.s5_generate_ideas
"""

import json
from workers.helpers import load_config, load_env, setup_logger, claude_call, parse_json_response
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


IDEA_PROMPT = """You are a product analyst finding SaaS opportunities for a 2-developer team.
Topic: "{topic}"

CONTEXT:
- Team: 2 developers (frontend + backend), both can orchestrate with AI
- Goal: find pain → build MVP in 2-4 weeks → validate demand → scale if works
- ONLY software products: SaaS, web service, API, browser extension, bot, CLI tool
- Revenue: subscription, one-time purchase, or freemium — NO marketplace, NO people-dependent models
- Target: Russia first, then international
- Must work WITHOUT network effects — product sells itself

PAIN CLUSTERS (sorted by pain_score):
{clusters_json}

TASK:
Generate 5-10 SaaS product ideas that solve these pains.

For each idea return JSON:
{{
  "title": "Product name (3-5 words)",
  "description": "What pain it solves and how. Why people will pay. (2-3 sentences, in Russian)",
  "product_example": "Concrete MVP: what UI, what it does, core feature (2-3 sentences, in Russian)",
  "solves_clusters": [1, 3],
  "feasibility": 7,
  "uniqueness": 8,
  "revenue_model": "subscription/freemium/one-time"
}}

SCORING GUIDE:

feasibility (1-10) — can 2 devs build MVP in 2-4 weeks:
  10: Landing + API, 1 week
  8-9: Web app with API + frontend, 2-3 weeks
  6-7: Needs integrations/data/ML, 3-4 weeks
  4-5: Complex infrastructure
  1-3: Needs 5+ people or 3+ months

uniqueness (1-10) — existing alternatives:
  10: Nothing like it exists
  8-9: Distant analogues, don't solve this exact pain
  6-7: Competitors exist but room to differentiate
  4-5: Many competitors
  1-3: Saturated market

HARD RULES:
- ONLY SaaS/tools — NO marketplaces, funds, insurance, communities, platforms-for-people
- NO ideas requiring physical operations or manual human work to function
- Each idea must solve at least 1 cluster
- Quality over quantity — 5 strong > 10 weak
- description and product_example MUST be in Russian

EXISTING IDEAS (don't repeat):
{existing_titles}

Return ONLY JSON array, no markdown."""


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
            "SELECT title FROM ideas WHERE created_at >= datetime('now', '-30 days')"
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

    prompt = IDEA_PROMPT.format(
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
            feasibility = min(max(idea.get("feasibility", 5), 1), 10)
            uniqueness = min(max(idea.get("uniqueness", 5), 1), 10)

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
                 solves_clusters, subreddits, is_duplicate)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    topic, title,
                    idea.get("description", ""),
                    idea.get("product_example", ""),
                    idea.get("revenue_model", ""),
                    score, round(demand_score, 2), round(breadth_score, 2),
                    feasibility, uniqueness,
                    json.dumps(solves), json.dumps(list(all_subs)),
                    dup_flag,
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
            """SELECT title, score, demand_score, feasibility_score, uniqueness_score, revenue_model
            FROM ideas WHERE topic=? AND is_duplicate=0 ORDER BY score DESC LIMIT 10""",
            (topic,),
        ).fetchall()
    print("\nТоп идеи:")
    for i in top:
        print(f"  [{i['score']:.1f}] {i['title']}")
        print(f"    demand={i['demand_score']:.1f} feasibility={i['feasibility_score']} uniqueness={i['uniqueness_score']} model={i['revenue_model']}")


if __name__ == "__main__":
    run()
