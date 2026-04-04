"""
All prompts for Claude API in one place.

Variables in {curly braces} are substituted via .format() in workers.
Double braces {{}} are escaped literals for JSON examples.
"""

# ─────────────────────────────────────────────
# S0 — Find subreddits
# ─────────────────────────────────────────────
S0_FIND_SUBREDDITS = """Find subreddits where people have problems related to "{topic}" that could be solved with a software product (SaaS, browser extension, bot, API, CLI tool).

You need subreddits where people:
- Complain about broken workflows, manual repetitive tasks, lack of tools
- Discuss existing tools and their shortcomings (= proven willingness to pay)
- Ask "is there a tool that does X?" or "how do I automate Y?"
- Share specific frustrations, not just vent emotions

GOOD signals (people would pay for a solution):
  r/cscareerquestions — "I spend hours tailoring each resume" (automatable pain)
  r/freelance — "invoicing clients is a nightmare" (clear SaaS opportunity)

BAD signals (no software product fits):
  r/rant — emotional venting, no actionable problem
  r/news — passive consumption, no pain
  r/askreddit — entertainment, not problem-solving

NOT needed: news, memes, emotional support, general discussion without actionable problems.

Return ONLY JSON, no markdown:
[{{"name": "subreddit name without r/", "why": "what software-solvable pain people discuss there", "relevance_score": 8}}]

Sort by relevance_score DESC. Max 20 subreddits."""

# ─────────────────────────────────────────────
# S3 — Extract pains from posts
# ─────────────────────────────────────────────
S3_ANALYZE_PAINS = """You extract user pain points from Reddit posts.

Research topic: {topic}

RULES:
Good pain — specific, with detail:
  + "I spend 3 hours a week manually updating spreadsheets"
  + "ATS systems reject my resume before a human ever sees it"
  + "I can't figure out why I get ghosted after the first interview"

Bad pain — abstract, no actionable hook:
  - "everything is hard"
  - "nobody responds"
  - "the job market is terrible"

IMPORTANT:
- Extract pains ONLY from the post text and comments
- Do NOT invent pains that aren't in the text
- If no pain exists — return empty problems array, do not fabricate
- One post can yield 0, 1, or several pains

Posts to analyze:
{posts_json}

LANGUAGE: All problem descriptions MUST be in Russian.

Return ONLY JSON, no markdown:
[{{"post_db_id": 123, "problems": ["конкретная боль на русском", "ещё одна боль на русском"]}}]"""

# ─────────────────────────────────────────────
# S4 — Cluster pains
# ─────────────────────────────────────────────
S4_CLUSTER_PROBLEMS = """You are a user pain analyst. Topic: "{topic}"

Below are {problems_count} user pain points from Reddit.
Many describe the same problem in different words.

TASK:
1. Group similar pains into clusters (5-20 clusters)
2. Give each a short name (3-5 words)
3. Write summary — essence of the pain in 1-2 sentences
4. Focus on pains solvable with software/SaaS

LANGUAGE: cluster_name and summary MUST be in Russian.

Return ONLY JSON, no markdown:
[{{"cluster_name": "Название кластера", "summary": "Суть проблемы", "problem_ids": [1, 5, 12]}}]

RULES:
- One pain can only be in one cluster
- No "Other" or "Miscellaneous" clusters
- Names must be specific: "ATS rejects resumes" not "Resume problems"

Pains:
{problems_json}"""

# ─────────────────────────────────────────────
# S5 — Generate ideas (runs on Sonnet)
# ─────────────────────────────────────────────
S5_GENERATE_IDEAS = """You are a product researcher. Find business ideas that solve real pains and can generate revenue.

Topic: {topic}

CONTEXT:
- Team: 2 developers (frontend + backend), both can orchestrate AI
- Goal: find pain → build MVP in 2-4 weeks → validate demand → scale
- ONLY software: SaaS, web service, API, browser extension, bot, CLI tool
- Revenue: subscription, one-time, freemium — NO marketplace, NO people-dependent models
- Must work WITHOUT network effects — product sells itself

PAIN CLUSTERS (sorted by pain_score):
{clusters_json}

---

BEFORE PROPOSING AN IDEA — kill it:

1. Who exactly will pay and why right now, not in a year?
2. Why haven't 10 funded startups solved this already?
3. Can this pain be closed with a free ChatGPT prompt?

If the idea survives these questions — it's strong.

---

CRITERIA:

Competition:
  medium = GOOD (demand proven, people pay)
  none = BAD (no market or pain isn't real)
  high = hard, need very clear advantage

Monetization — numbers only:
  NO: "subscription"
  YES: "freemium: 5 uses free, $9/mo unlimited"

Where we meet the user — be specific:
  NO: "during their workflow"
  YES: "on the job listing page on LinkedIn"
  YES: "the moment they receive a rejection email"

feasibility (1-10) — can 2 devs build MVP in 2-4 weeks:
  10: Landing + API, 1 week
  8-9: Web app with API + frontend, 2-3 weeks
  6-7: Needs integrations/data/ML, 3-4 weeks
  4-5: Complex infrastructure
  1-3: Needs 5+ people or 3+ months

uniqueness (1-10) — existing alternatives:
  10: Nothing like it exists
  8-9: Distant analogues
  6-7: Competitors exist but room to differentiate
  4-5: Many competitors
  1-3: Saturated market

---

Existing ideas from last 30 days (do not repeat):
{existing_titles}

---

HOW MANY IDEAS:
- Minimum 3, maximum 10
- Better 4 honest than 8 stretched
- If an idea is weak — don't include it

---

LANGUAGE: ALL text fields (title, pain, solution, description, product_example, where_we_meet_user, monetization, competition_note, validation_step) MUST be in Russian.

Return ONLY JSON, no markdown:
[{{
  "title": "конкретное название продукта",
  "pain": "одно предложение: какая боль и где возникает",
  "solution": "одно предложение: что делает продукт",
  "description": "2-3 предложения подробнее",
  "product_example": "конкретный MVP: UI, функция, ключевая фича (2-3 предложения)",
  "where_we_meet_user": "конкретный момент и место где пользователь страдает",
  "monetization": "конкретная модель с цифрами",
  "monetization_type": "saas_subscription | one_time | freemium | b2b_license",
  "revenue_model": "subscription",
  "competition_level": "none | low | medium | high",
  "competition_note": "кто конкуренты и в чём наше преимущество",
  "validation_step": "одно действие на 2 часа чтобы проверить спрос",
  "solves_clusters": [1, 3],
  "feasibility": 7,
  "uniqueness": 8
}}]"""

# ─────────────────────────────────────────────
# Deep Analysis — deep dive on a single idea
# ─────────────────────────────────────────────
DEEP_ANALYSIS = """You are a devil's advocate and strategist.

Analyze this business idea honestly and ruthlessly:

Idea: {title}
Pain: {pain}
Solution: {solution}
Where we meet user: {where_we_meet_user}
Monetization: {monetization}
Competition: {competition_level} — {competition_note}

---

ANALYSIS STRUCTURE:

1. COMPETITORS (from your knowledge)
   Name real products that already solve this pain.
   For each: approximate price, main weakness.
   If you don't know specific ones — say so honestly.

2. MARKET SIZE (rough)
   How many people have this pain?
   How many are willing to pay?
   Rough annual revenue estimate at 1%% conversion.

3. WHERE TO GET FIRST 10 USERS
   Specific places: which subreddits, Slack/Discord groups,
   Twitter search, ProductHunt, LinkedIn filters.
   Not "find target audience" but literally where these people hang out.

4. MVP IN 2 WEEKS
   Minimum feature set that can already be sold.
   Tech stack (specific, not abstract).
   What NOT to build in v1.

5. KEY RISK
   One thing that kills this idea if not validated.
   How to validate this exact risk in 48 hours without code.

6. VERDICT
   One line: do it / don't do it / do it if [condition]

---

LANGUAGE: Write entire analysis in Russian.
Be brief and specific. No filler.
If you don't know something — say so honestly, don't fabricate."""

# ─────────────────────────────────────────────
# Test flow — batch file instruction for Claude Code
# ─────────────────────────────────────────────
TEST_BATCH_PROMPT = (
    "Analyze the posts below. For each one find specific user pain points. "
    "Write to data/miner.db table problems (raw_post_id, subreddit, problem, upvotes, source_url). "
    "Mark posts as processed=1 in raw_posts."
)
