"""
Все промпты для Claude API в одном месте.

Переменные в фигурных скобках подставляются через .format() в воркерах.
"""

# S0 — Поиск сабреддитов
S0_FIND_SUBREDDITS = """Find 15-20 subreddits on Reddit where people discuss problems related to: "{topic}"

I need subreddits where users COMPLAIN, ask for help, discuss what doesn't work.
Not news or entertainment subreddits.

Return ONLY a JSON array, no markdown:
[{{"name": "subredditname", "relevance_score": 9}}]
Sort by relevance_score DESC. Use real subreddit names without r/ prefix."""

# S3 — Анализ болей из постов
S3_ANALYZE_PAINS = """You analyze Reddit posts to find user pain points that can be solved with software.

For each post, extract ONLY specific pains:
- What doesn't work, what frustrates, what people want improved
- Focus on pains solvable by a SaaS tool, web service, API, browser extension, or bot
- Ignore: vague complaints, political opinions, emotional venting without actionable problem

Posts:
{posts_json}

Return ONLY JSON array, no markdown:
[{{"post_db_id": 123, "subreddit": "jobs", "problems": ["pain 1", "pain 2"], "url": "https://..."}}]
Empty problems array if no software-solvable pains found."""

# S4 — Кластеризация болей
S4_CLUSTER_PROBLEMS = """You are a user pain analyst. Topic: "{topic}"

Below are {problems_count} user pain points from Reddit.
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
{problems_json}"""

# S5 — Генерация SaaS-идей (с расширенной оценкой)
S5_GENERATE_IDEAS = """You are an expert at finding business ideas and product-market fit.
Topic: "{topic}"

CONTEXT:
- Team: 2 developers (frontend + backend), both can orchestrate with AI
- Goal: find pain → build MVP in 2-4 weeks → validate demand → scale if works
- ONLY software products: SaaS, web service, API, browser extension, bot, CLI tool
- Target: Russia first, then international
- Must work WITHOUT network effects — product sells itself

CRITERIA FOR A GOOD IDEA:
- Moderate competition = GOOD (demand is proven)
- Zero competition = BAD (no market exists)
- Must have an obvious place where we meet the user
- Monetization must be specific, not abstract

PAIN CLUSTERS (sorted by pain_score):
{clusters_json}

TASK:
Find SaaS product ideas that solve these pains.
Be strict: better 3 strong ideas than 10 weak ones.
Minimum 3, maximum — as many as genuinely strong.

For each idea return JSON (ALL text fields in Russian):
{{
  "title": "Конкретное название продукта",
  "pain": "Одно предложение: какая боль и где возникает",
  "solution": "Что делает продукт, в одном предложении",
  "where_we_meet_user": "Конкретное место/момент где пользователь страдает. Например: страница вакансии на LinkedIn, письмо от клиента в Gmail",
  "monetization": "Конкретная модель с цифрами: freemium $0/$9/$29 мес, или $49 разово, или $199/мес b2b",
  "monetization_type": "saas_subscription | one_time | freemium | b2b_license",
  "competition_level": "none | low | medium | high",
  "competition_note": "Кто конкуренты и почему наш вариант лучше",
  "validation_step": "Конкретный первый шаг валидации за 48 часов",
  "solves_clusters": [1, 3],
  "score": 8,
  "feasibility": 7,
  "uniqueness": 8,
  "feasibility_breakdown": {{
    "tech_complexity": 8,
    "data_availability": 9,
    "third_party_deps": 7,
    "legal_risk": 9,
    "mvp_scope": "Что входит в MVP, что отложить на потом (1-2 предложения)"
  }}
}}

SCORING GUIDE:

score (1-10) — overall potential:
  9-10: Clear pain, proven demand, easy MVP, obvious monetization
  7-8: Strong idea, some unknowns
  5-6: Interesting but risky
  1-4: Weak or unclear

feasibility (1-10) — COMPOSITE score based on these sub-factors:

  tech_complexity (1-10) — technical difficulty for 2 fullstack devs + AI:
    10: Static site, simple CRUD, basic API
    8-9: Standard web app with auth, payments, simple ML/AI calls
    6-7: Complex integrations, real-time features, custom ML models
    4-5: Distributed systems, heavy data processing
    1-3: Requires PhD-level research or years of data collection

  data_availability (1-10) — is the data needed for the product accessible:
    10: Public APIs, no data needed, user generates content
    8-9: Freely available data, easy to scrape/aggregate
    6-7: Paid APIs, partial data, needs enrichment
    4-5: Hard to get data, partnerships required
    1-3: Proprietary data, regulatory barriers

  third_party_deps (1-10) — dependency on external services/platforms:
    10: Self-contained, no external deps
    8-9: Standard cloud services (AWS, Stripe, etc.)
    6-7: Depends on specific platform APIs (LinkedIn, HH, etc.) that may break
    4-5: Depends on unstable or rate-limited APIs
    1-3: Requires platform approval, partnership, or enterprise contract

  legal_risk (1-10) — legal/compliance concerns:
    10: No legal issues
    8-9: Standard terms of service compliance
    6-7: Gray area (scraping, data privacy, user content)
    4-5: Needs legal review, GDPR/privacy concerns
    1-3: Potential lawsuits, regulatory approval needed

  mvp_scope: what's IN the MVP vs what's deferred (in Russian)

  Final feasibility = average of (tech_complexity + data_availability + third_party_deps + legal_risk) / 4
  IMPORTANT: Be HONEST. If the idea needs scraping LinkedIn — third_party_deps is 4-5, not 8.
  If it records private conversations — legal_risk is 3-4, not 8.

uniqueness (1-10) — market position:
  10: Nothing exists
  8-9: Distant analogues
  6-7: Competitors but room to differentiate
  4-5: Many competitors
  1-3: Saturated

HARD RULES:
- ONLY SaaS/tools — NO marketplaces, funds, insurance, communities
- NO ideas requiring manual human work to function
- Each idea must solve at least 1 cluster
- ALL text fields MUST be in Russian
- competition_level "medium" is BETTER than "none" (proven demand)

EXISTING IDEAS (don't repeat):
{existing_titles}

Return ONLY JSON array, no markdown."""

# Deep Analysis — глубокий анализ одной идеи
DEEP_ANALYSIS = """You are a startup analyst doing deep due diligence on a product idea.

IDEA:
Title: {title}
Pain: {pain}
Solution: {solution}
Where we meet user: {where_we_meet_user}
Monetization: {monetization}
Competition level: {competition_level}

TASK — answer in Russian, be specific and honest:

1. КОНКУРЕНТЫ
   - Кто уже делает похожее? (названия, ссылки если знаешь)
   - Сколько стоят их решения?
   - Их слабые места?

2. РЫНОК
   - TAM/SAM грубая оценка
   - Кто платит: B2C или B2B?
   - Средний чек и LTV

3. ПЕРВЫЕ 10 ПОЛЬЗОВАТЕЛЕЙ
   - Где их искать конкретно?
   - Какой канал привлечения самый дешёвый?
   - Как превратить в платящих?

4. MVP ЗА 2 НЕДЕЛИ
   - Технический стек
   - Что включить в MVP, что отложить
   - Главные технические риски

5. ГЛАВНЫЙ РИСК
   - Что может убить идею?
   - Как проверить за 48 часов?

Return plain text, structured with headers. Be brutally honest."""

# Test flow — инструкция для батч-файлов
TEST_BATCH_PROMPT = (
    "Проанализируй посты ниже. Для каждого найди конкретные боли пользователей. "
    "Запиши в data/miner.db таблица problems (raw_post_id, subreddit, problem, upvotes, source_url). "
    "Пометь посты processed=1 в raw_posts."
)
