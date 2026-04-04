"""
S5 — Генерация идей через Claude Sonnet + скоринг + дедупликация.

Берёт топ кластеры болей, отправляет в Claude Sonnet для генерации идей,
считает финальный score по формуле, дедуплицирует, сохраняет в таблицу ideas.

python3 -m workers.s5_generate_ideas
"""

import json
import math
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

    clusters_for_prompt = []
    for c in clusters:
        clusters_for_prompt.append({
            "id": c["id"],
            "name": c["cluster_name"],
            "summary": c["summary"],
            "pain_score": c["pain_score"],
            "frequency": c["frequency"],
            "subreddit_spread": c["subreddit_spread"],
            "subreddits": json.loads(c["subreddits_json"]) if c["subreddits_json"] else [],
        })

    existing_titles = [r["title"] for r in existing_ideas]

    prompt = f"""Ты продуктовый аналитик. Ищешь возможности для быстрого MVP.
Тема: "{topic}"

КОНТЕКСТ:
Команда — 2 разработчика (фронтенд + бэкенд), оба могут оркестрировать.
Цель — найти боль, сделать MVP за 2-4 недели, проверить спрос.
Если стрельнёт — масштабировать. Ресурсы для масштабирования есть.

КЛАСТЕРЫ БОЛЕЙ (отсортированы по pain_score):
{json.dumps(clusters_for_prompt, ensure_ascii=False, indent=2)}

ЗАДАНИЕ:
Найди 5-15 продуктовых идей, которые решают эти боли.

Для каждой идеи верни JSON:
{{
  "title": "Название (3-5 слов)",
  "description": "Какую боль решает и как. Почему люди будут платить. (2-3 предложения)",
  "product_example": "Что строим: интерфейс, функции, как выглядит MVP (2-3 предложения)",
  "solves_clusters": [1, 3],
  "feasibility": 7,
  "uniqueness": 8,
  "revenue_model": "подписка/freemium/разовая/marketplace"
}}

МЕТОДОЛОГИЯ ОЦЕНКИ:

feasibility (1-10) — реально ли 2 разработчикам собрать MVP за 2-4 недели:
  10: Лендинг + API, можно за неделю
  8-9: Веб-сервис, API + фронт, 2-3 недели
  6-7: Нужны интеграции/данные, 3-4 недели
  4-5: Сложная инфраструктура
  1-3: Нужна команда 5+ или 3+ месяца

uniqueness (1-10) — есть ли аналоги:
  10: Ничего подобного нет
  8-9: Далёкие аналоги, не решают эту боль
  6-7: Есть конкуренты, можно дифференцироваться
  4-5: Много конкурентов
  1-3: Рынок перенасыщен

ПРАВИЛА:
- НЕ генерируй "платформу для всего" — только конкретные узкие продукты
- Каждая идея решает хотя бы 1 кластер
- Лучше 5 сильных чем 15 слабых

СУЩЕСТВУЮЩИЕ ИДЕИ (не повторяй):
{json.dumps(existing_titles, ensure_ascii=False)}

Верни ТОЛЬКО JSON массив, без markdown."""

    logger.info(f"S5: sending {len(clusters)} clusters to Claude for idea generation")
    raw = claude_call("claude-sonnet-4-6-20250514", prompt, config, logger)

    try:
        ideas = parse_json_response(raw, logger)
    except json.JSONDecodeError as e:
        logger.error(f"S5: Claude returned invalid JSON: {e}")
        return

    # Скоринг + дедупликация + запись в БД
    saved = 0
    duplicates = 0

    with use_conn() as conn:
        for idea in ideas:
            title = idea.get("title", "Untitled")

            # Дедупликация
            dup_flag = 1 if is_duplicate(title, existing_titles, dedup_threshold) else 0
            if dup_flag:
                duplicates += 1

            # Скоринг
            solves = idea.get("solves_clusters", [])
            feasibility = min(max(idea.get("feasibility", 5), 1), 10)
            uniqueness = min(max(idea.get("uniqueness", 5), 1), 10)

            # demand_score: средний pain_score решаемых кластеров, нормализованный к 10
            solved_pain = [clusters_dict[cid]["pain_score"] for cid in solves if cid in clusters_dict]
            demand_score = (sum(solved_pain) / len(solved_pain)) / max_pain_score * 10 if solved_pain else 0

            # breadth_score: сколько кластеров покрывает
            breadth_score = min(len(solves) / max(len(clusters_dict) * 0.3, 1) * 10, 10)

            # Финальный score
            score = round(
                demand_score * 0.35 + breadth_score * 0.25 + feasibility * 0.20 + uniqueness * 0.20,
                2,
            )

            # Сабреддиты из кластеров
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
                    score,
                    round(demand_score, 2),
                    round(breadth_score, 2),
                    feasibility, uniqueness,
                    json.dumps(solves),
                    json.dumps(list(all_subs)),
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

    # Топ идеи
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
