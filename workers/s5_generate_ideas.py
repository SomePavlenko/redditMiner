"""
S5 — Генерация и скоринг идей.

Флоу:
  1. python3 -m workers.s5_generate_ideas           → готовит data/ideas_prompt.json
  2. Claude Code читает, генерит идеи              → сохраняет data/ideas_raw.json
  3. python3 -m workers.s5_generate_ideas --save    → скоринг + дедуп + INSERT в БД

Формат data/ideas_raw.json (Claude Code создаёт):
[
  {
    "title": "Название",
    "description": "Описание",
    "product_example": "Как выглядит MVP",
    "solves_clusters": [1, 3, 7],
    "feasibility": 7,
    "uniqueness": 8,
    "revenue_model": "подписка"
  }
]

python3 -m workers.s5_generate_ideas              # подготовить промпт
python3 -m workers.s5_generate_ideas --save       # финализировать + записать в БД
"""

import json
import math
import os
import sys
from workers.helpers import load_config, setup_logger, ROOT
from workers.db import use_conn

IDEAS_PROMPT_FILE = os.path.join(ROOT, "data", "ideas_prompt.json")
IDEAS_RAW_FILE = os.path.join(ROOT, "data", "ideas_raw.json")


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


def prepare_prompt():
    """Готовит промпт для генерации идей через Claude Code."""
    config = load_config()
    logger = setup_logger("s5")
    topic = config["topic"]

    with use_conn() as conn:
        clusters = conn.execute(
            "SELECT * FROM pain_clusters WHERE topic=? ORDER BY pain_score DESC",
            (topic,),
        ).fetchall()

        existing_ideas = conn.execute(
            "SELECT title FROM ideas WHERE created_at >= datetime('now', '-30 days')"
        ).fetchall()

    if not clusters:
        print("Нет кластеров болей. Сначала запусти S4.")
        return

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

    prompt_data = {
        "_prompt": f"""Ты продуктовый аналитик. Ищешь возможности для быстрого MVP.
Тема исследования: "{topic}"

КОНТЕКСТ:
Команда — 2 разработчика (фронтенд + бэкенд), оба могут оркестрировать.
Цель — найти боль, сделать MVP за 2-4 недели, проверить спрос.
Если стрельнёт — масштабировать. Если нет — следующая идея.
Ресурсы для масштабирования есть.

КЛАСТЕРЫ БОЛЕЙ (отсортированы по pain_score):
(pain_score = частота упоминаний + охват сабреддитов + популярность)

{json.dumps(clusters_for_prompt, ensure_ascii=False, indent=2)}

ЗАДАНИЕ:
Найди 5-15 продуктовых идей, которые решают эти боли.

Для каждой идеи верни JSON:
{{
  "title": "Название (3-5 слов)",
  "description": "Какую боль решает и как. Почему люди будут платить. (2-3 предложения)",
  "product_example": "Конкретно что строим: какой интерфейс, что делает, как выглядит MVP (2-3 предложения)",
  "solves_clusters": [1, 3],
  "feasibility": 7,
  "uniqueness": 8,
  "revenue_model": "подписка/freemium/разовая/marketplace"
}}

МЕТОДОЛОГИЯ ОЦЕНКИ:

feasibility (1-10) — Насколько реально двум разработчикам собрать MVP за 2-4 недели:
  10: Лендинг + простой бэкенд, можно за неделю
  8-9: Стандартный веб-сервис, API + фронт, 2-3 недели
  6-7: Нужны интеграции/данные/ML, 3-4 недели
  4-5: Сложная инфраструктура, но возможно
  1-3: Нужна команда 5+ человек или 3+ месяца

uniqueness (1-10) — Есть ли аналоги и насколько идея свежая:
  10: Ничего подобного нет
  8-9: Есть далёкие аналоги, но не решают именно эту боль
  6-7: Есть конкуренты, но можно дифференцироваться
  4-5: Много конкурентов, нужен уникальный угол
  1-3: Рынок перенасыщен

ПРАВИЛА:
- НЕ генерируй "платформу для всего" — только конкретные узкие продукты
- Каждая идея должна решать хотя бы 1 кластер с pain_score > медианы
- Лучше 5 сильных идей чем 15 слабых
- MVP должен быть реально строимым, не фантазией

СУЩЕСТВУЮЩИЕ ИДЕИ (не повторяй похожие):
{json.dumps(existing_titles, ensure_ascii=False)}

Сохрани результат как JSON массив в файл data/ideas_raw.json""",
    }

    with open(IDEAS_PROMPT_FILE, "w", encoding="utf-8") as f:
        json.dump(prompt_data, f, ensure_ascii=False, indent=2)

    logger.info(f"S5: prepared prompt with {len(clusters)} clusters")
    print(f"Промпт готов: {IDEAS_PROMPT_FILE} ({len(clusters)} кластеров)")
    print(f'\nОткрой Claude Code:')
    print(f'  "Прочитай {IDEAS_PROMPT_FILE}, выполни _prompt"')


def save_ideas():
    """Читает ideas_raw.json, считает скоринг, дедуплицирует, пишет в БД."""
    config = load_config()
    logger = setup_logger("s5")
    topic = config["topic"]
    dedup_threshold = config.get("idea_dedup_similarity_threshold", 0.6)

    if not os.path.exists(IDEAS_RAW_FILE):
        print(f"Файл {IDEAS_RAW_FILE} не найден. Сначала запусти Claude Code.")
        return

    with open(IDEAS_RAW_FILE, encoding="utf-8") as f:
        ideas = json.load(f)

    # Загружаем кластеры для расчёта demand и breadth
    with use_conn() as conn:
        clusters = {
            row["id"]: dict(row)
            for row in conn.execute("SELECT * FROM pain_clusters WHERE topic=?", (topic,)).fetchall()
        }
        existing_titles = [
            r["title"]
            for r in conn.execute("SELECT title FROM ideas WHERE created_at >= datetime('now', '-30 days')").fetchall()
        ]

    if not clusters:
        print("Нет кластеров в БД. Сначала S4 --save.")
        return

    max_pain_score = max(c["pain_score"] for c in clusters.values()) if clusters else 1

    saved = 0
    duplicates = 0

    with use_conn() as conn:
        for idea in ideas:
            title = idea.get("title", "Untitled")

            # Дедупликация
            if is_duplicate(title, existing_titles, dedup_threshold):
                duplicates += 1
                dup_flag = 1
            else:
                dup_flag = 0

            # Скоринг
            solves = idea.get("solves_clusters", [])
            feasibility = min(max(idea.get("feasibility", 5), 1), 10)
            uniqueness = min(max(idea.get("uniqueness", 5), 1), 10)

            # demand_score: средний pain_score решаемых кластеров, нормализованный к 10
            solved_pain_scores = [clusters[cid]["pain_score"] for cid in solves if cid in clusters]
            if solved_pain_scores:
                demand_score = (sum(solved_pain_scores) / len(solved_pain_scores)) / max_pain_score * 10
            else:
                demand_score = 0

            # breadth_score: сколько кластеров покрывает, нормализованный к 10
            breadth_score = min(len(solves) / max(len(clusters) * 0.3, 1) * 10, 10)

            # Финальный score: demand 35% + breadth 25% + feasibility 20% + uniqueness 20%
            score = round(
                demand_score * 0.35 + breadth_score * 0.25 + feasibility * 0.20 + uniqueness * 0.20,
                2,
            )

            # Собираем сабреддиты из кластеров
            all_subs = set()
            all_urls = []
            for cid in solves:
                if cid in clusters:
                    c = clusters[cid]
                    try:
                        all_subs.update(json.loads(c["subreddits_json"]))
                    except (json.JSONDecodeError, TypeError):
                        pass

            conn.execute(
                """INSERT INTO ideas
                (topic, title, description, product_example, revenue_model,
                 score, demand_score, breadth_score, feasibility_score, uniqueness_score,
                 solves_clusters, subreddits, is_duplicate)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    topic,
                    title,
                    idea.get("description", ""),
                    idea.get("product_example", ""),
                    idea.get("revenue_model", ""),
                    score,
                    round(demand_score, 2),
                    round(breadth_score, 2),
                    feasibility,
                    uniqueness,
                    json.dumps(solves),
                    json.dumps(list(all_subs)),
                    dup_flag,
                ),
            )

            if not dup_flag:
                saved += 1
                # Обновляем вес сабреддитов
                for sub_name in all_subs:
                    conn.execute(
                        "UPDATE subreddits SET weight = weight + ?, total_ideas = total_ideas + 1 WHERE name=?",
                        (score * 0.1, sub_name),
                    )

            existing_titles.append(title)

        conn.commit()

    logger.info(f"S5: saved {saved} ideas, {duplicates} duplicates")
    print(f"\nСохранено: {saved} идей, {duplicates} дубликатов пропущено")

    # Показываем топ
    with use_conn() as conn:
        top = conn.execute(
            "SELECT title, score, demand_score, feasibility_score, uniqueness_score, revenue_model FROM ideas WHERE topic=? AND is_duplicate=0 ORDER BY score DESC LIMIT 10",
            (topic,),
        ).fetchall()
    print("\nТоп идеи:")
    for i in top:
        print(f"  [{i['score']:.1f}] {i['title']}")
        print(f"    demand={i['demand_score']:.1f} feasibility={i['feasibility_score']} uniqueness={i['uniqueness_score']} model={i['revenue_model']}")

    os.rename(IDEAS_RAW_FILE, IDEAS_RAW_FILE + ".done")


def run():
    if "--save" in sys.argv:
        save_ideas()
    else:
        prepare_prompt()


if __name__ == "__main__":
    run()
