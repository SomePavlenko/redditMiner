# Reddit Miner Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build an autonomous system that mines Reddit for user pain points, generates business ideas via Claude API, and delivers daily digests via Telegram — with a React dashboard for exploration.

**Architecture:** Python workers run sequentially (W0→W4) via cron, each reading/writing SQLite. FastAPI serves data to a React/Vite frontend. Claude Haiku handles batch analysis (cheap), Sonnet handles idea synthesis (quality). Reddit OAuth2 client_credentials for API access.

**Tech Stack:** Python 3.11+, FastAPI, SQLite (WAL), React 18, Vite, Tailwind CSS, Recharts, Claude API (anthropic SDK), httpx, python-telegram-bot

---

### Task 1: Foundation — CLAUDE.md, config, env, DB schema, folder structure

**Files:**
- Create: `CLAUDE.md`
- Create: `config.json`
- Create: `.env.example`
- Create: `workers/__init__.py`
- Create: `workers/db.py` (shared DB init + helpers)
- Create: `api/__init__.py`
- Modify: `.gitignore` (add data/, logs/, .topic_hash, .env)

**Step 1: Create CLAUDE.md**

```markdown
# Reddit Miner — контекст проекта

## Что это
Автономная система поиска бизнес-идей через парсинг болей пользователей Reddit.
Запускается ночью по cron, результаты приходят в Telegram утром.

## Стек
- Python 3.11+ — все воркеры и FastAPI
- SQLite (WAL mode) — основная БД, файл data/miner.db
- React + Vite + Tailwind + Recharts — фронтенд на localhost:3000
- FastAPI — REST API на localhost:8000
- Claude API: Haiku для батчей (дёшево), Sonnet для дайджеста (качество)
- Reddit OAuth2 client_credentials — без логина пользователя

## Воркеры и порядок запуска
1. W0 — topic agent (разово при смене topic в config.json)
2. W1 — parser (02:00 по cron)
3. W2 — analyzer (03:00 по cron)
4. W3 — digest + Telegram (04:00 по cron)
5. W4 — reparse suggestions (05:00 по cron)

Для первого запуска: python workers/run_all.py

## Важные соглашения
- Все параметры только из config.json и .env, никаких хардкодов
- Каждый воркер логирует в logs/{worker}_{date}.log
- SQLite WAL mode включён при инициализации БД
- Claude API вызовы: retry 3 раза с backoff 2s
- Reddit OAuth токен: автоматический refresh при истечении (expires_in - 60s)
- W0 определяет смену topic через MD5 hash в файле .topic_hash

## Статус разработки
- [ ] Структура папок и БД
- [ ] W0 topic agent
- [ ] W1 parser
- [ ] W2 analyzer
- [ ] W3 digest + TG
- [ ] W4 reparse
- [ ] FastAPI
- [ ] React frontend
- [ ] setup.sh + cron
```

**Step 2: Create config.json**

```json
{
  "topic": "job search",
  "min_upvotes": 50,
  "reddit_posts_per_request": 100,
  "claude_batch_size": 20,
  "digest_min_ideas": 3,
  "idea_score_threshold": 7,
  "idea_dedup_similarity_threshold": 0.6,
  "reparse_days": 7,
  "claude_retry_attempts": 3,
  "claude_retry_backoff_seconds": 2,
  "cron_parser": "0 2 * * *",
  "cron_analyzer": "0 3 * * *",
  "cron_digest": "0 4 * * *",
  "cron_reparse_check": "0 5 * * *"
}
```

**Step 3: Create .env.example**

```
ANTHROPIC_API_KEY=
REDDIT_CLIENT_ID=
REDDIT_CLIENT_SECRET=
REDDIT_USER_AGENT=reddit-miner/1.0 by /u/yourusername
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

**Step 4: Create workers/db.py — shared DB module**

```python
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "miner.db")

def get_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db():
    conn = get_conn()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS subreddits (
      id INTEGER PRIMARY KEY,
      name TEXT UNIQUE NOT NULL,
      topic TEXT NOT NULL,
      weight REAL DEFAULT 0,
      last_parsed_at TEXT,
      total_ideas INTEGER DEFAULT 0,
      queue_reparse INTEGER DEFAULT 0,
      active INTEGER DEFAULT 1,
      created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS raw_posts (
      id INTEGER PRIMARY KEY,
      reddit_id TEXT UNIQUE NOT NULL,
      subreddit TEXT NOT NULL,
      title TEXT,
      body TEXT,
      url TEXT,
      upvotes INTEGER DEFAULT 0,
      comments_json TEXT,
      parsed_at TEXT DEFAULT CURRENT_TIMESTAMP,
      processed INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS problems (
      id INTEGER PRIMARY KEY,
      raw_post_id INTEGER REFERENCES raw_posts(id),
      subreddit TEXT,
      problem TEXT NOT NULL,
      upvotes INTEGER DEFAULT 0,
      source_url TEXT,
      parsed_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS ideas (
      id INTEGER PRIMARY KEY,
      topic TEXT NOT NULL,
      title TEXT NOT NULL,
      description TEXT,
      product_example TEXT,
      score REAL DEFAULT 0,
      market_score INTEGER DEFAULT 0,
      difficulty_score INTEGER DEFAULT 0,
      uniqueness_score INTEGER DEFAULT 0,
      source_urls TEXT,
      subreddits TEXT,
      is_favourite INTEGER DEFAULT 0,
      is_duplicate INTEGER DEFAULT 0,
      created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS digests (
      id INTEGER PRIMARY KEY,
      topic TEXT NOT NULL,
      ideas_json TEXT,
      sent_to_tg INTEGER DEFAULT 0,
      created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)
    conn.close()
```

**Step 5: Create __init__.py files, update .gitignore, create directories**

Run:
```bash
mkdir -p workers api data logs
touch workers/__init__.py api/__init__.py
```

Update `.gitignore` to add:
```
data/miner.db
logs/
.topic_hash
```

**Step 6: Test DB init**

Run: `python -c "from workers.db import init_db; init_db(); print('OK')"`
Expected: OK, file `data/miner.db` exists

**Step 7: Commit**

```bash
git add CLAUDE.md config.json .env.example .gitignore workers/ api/ docs/
git commit -m "feat: project foundation — CLAUDE.md, config, DB schema, folder structure"
```

---

### Task 2: W0 — Topic Agent (workers/w0_topic.py)

**Files:**
- Create: `workers/w0_topic.py`
- Create: `workers/helpers.py` (shared logging, config loading, Claude retry)

**Step 1: Create workers/helpers.py — shared utilities**

```python
import json
import os
import logging
import time
from datetime import datetime
from dotenv import load_dotenv
import anthropic

ROOT = os.path.join(os.path.dirname(__file__), "..")

def load_config():
    with open(os.path.join(ROOT, "config.json")) as f:
        return json.load(f)

def save_config(config):
    with open(os.path.join(ROOT, "config.json"), "w") as f:
        json.dump(config, f, indent=2)

def load_env():
    load_dotenv(os.path.join(ROOT, ".env"))

def setup_logger(worker_name):
    os.makedirs(os.path.join(ROOT, "logs"), exist_ok=True)
    log_file = os.path.join(ROOT, "logs", f"{worker_name}_{datetime.now().strftime('%Y%m%d')}.log")
    logger = logging.getLogger(worker_name)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        fh = logging.FileHandler(log_file)
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(fh)
        sh = logging.StreamHandler()
        sh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(sh)
    return logger

def claude_call(model, prompt, config, logger):
    load_env()
    client = anthropic.Anthropic()
    for attempt in range(config["claude_retry_attempts"]):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text
        except Exception as e:
            logger.warning(f"Claude API attempt {attempt+1} failed: {e}")
            if attempt < config["claude_retry_attempts"] - 1:
                time.sleep(config["claude_retry_backoff_seconds"] * (attempt + 1))
            else:
                raise
```

**Step 2: Create workers/w0_topic.py**

```python
import hashlib
import json
import os
import httpx
from workers.helpers import load_config, setup_logger, claude_call, ROOT
from workers.db import get_conn

TOPIC_HASH_FILE = os.path.join(ROOT, ".topic_hash")

def get_topic_hash(topic):
    return hashlib.md5(topic.encode()).hexdigest()

def topic_changed(topic):
    current_hash = get_topic_hash(topic)
    if os.path.exists(TOPIC_HASH_FILE):
        with open(TOPIC_HASH_FILE) as f:
            return f.read().strip() != current_hash
    return True

def save_topic_hash(topic):
    with open(TOPIC_HASH_FILE, "w") as f:
        f.write(get_topic_hash(topic))

def fetch_claude_subreddits(topic, config, logger):
    prompt = f"""Find the top 20 subreddits on Reddit for discovering business ideas related to '{topic}'.
Return ONLY a JSON array, no markdown: [{{"name": "subredditname", "estimated_members": 100000, "relevance_score": 9}}]
Sort by relevance_score DESC. Use real subreddit names without r/ prefix."""
    raw = claude_call("claude-haiku-4-5-20250901", prompt, config, logger)
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
    return json.loads(raw)

def fetch_reddit_subreddits(topic, logger):
    try:
        resp = httpx.get(
            f"https://www.reddit.com/subreddits/search.json?q={topic}&limit=10",
            headers={"User-Agent": "reddit-miner/1.0"},
            timeout=15
        )
        resp.raise_for_status()
        results = []
        for child in resp.json()["data"]["children"]:
            d = child["data"]
            results.append({
                "name": d["display_name"],
                "estimated_members": d.get("subscribers", 0),
                "relevance_score": 5
            })
        return results
    except Exception as e:
        logger.warning(f"Reddit search failed: {e}")
        return []

def run(force=False):
    config = load_config()
    topic = config["topic"]
    logger = setup_logger("w0")

    if not force and not topic_changed(topic):
        logger.info(f"W0: topic '{topic}' unchanged, skipping")
        return

    logger.info(f"W0: starting for topic '{topic}'")

    claude_subs = fetch_claude_subreddits(topic, config, logger)
    reddit_subs = fetch_reddit_subreddits(topic, logger)

    # Deduplicate by name (lowercase)
    seen = {}
    for s in claude_subs + reddit_subs:
        key = s["name"].lower()
        if key not in seen or s["relevance_score"] > seen[key]["relevance_score"]:
            seen[key] = s

    merged = sorted(seen.values(), key=lambda x: x["relevance_score"], reverse=True)

    conn = get_conn()
    conn.execute("UPDATE subreddits SET active=0 WHERE topic=?", (topic,))
    for s in merged:
        conn.execute("""
            INSERT INTO subreddits (name, topic, weight, active)
            VALUES (?, ?, ?, 1)
            ON CONFLICT(name) DO UPDATE SET topic=?, weight=?, active=1
        """, (s["name"], topic, s["relevance_score"], topic, s["relevance_score"]))
    conn.commit()
    conn.close()

    save_topic_hash(topic)
    logger.info(f"W0: found {len(merged)} subreddits for topic '{topic}'")

if __name__ == "__main__":
    import sys
    run(force="--force" in sys.argv)
```

**Step 3: Test W0**

Run: `python -m workers.w0_topic --force`
Expected: Logs showing subreddits found, DB populated. Check with:
`python -c "from workers.db import get_conn; c=get_conn(); print([dict(r) for r in c.execute('SELECT name, weight FROM subreddits WHERE active=1').fetchall()])"`

**Step 4: Commit**

```bash
git add workers/
git commit -m "feat: W0 topic agent — finds subreddits via Claude + Reddit search"
```

---

### Task 3: W1 — Reddit Parser (workers/w1_parser.py)

**Files:**
- Create: `workers/w1_parser.py`

**Step 1: Create workers/w1_parser.py**

```python
import os
import time
import json
import httpx
from datetime import datetime
from workers.helpers import load_config, load_env, setup_logger, ROOT
from workers.db import get_conn

class RedditAuth:
    def __init__(self):
        self.token = None
        self.expires_at = 0

    def get_token(self):
        if time.time() >= self.expires_at:
            self._refresh()
        return self.token

    def _refresh(self):
        resp = httpx.post(
            "https://www.reddit.com/api/v1/access_token",
            auth=(os.environ["REDDIT_CLIENT_ID"], os.environ["REDDIT_CLIENT_SECRET"]),
            data={"grant_type": "client_credentials"},
            headers={"User-Agent": os.environ["REDDIT_USER_AGENT"]},
            timeout=15
        )
        resp.raise_for_status()
        data = resp.json()
        self.token = data["access_token"]
        self.expires_at = time.time() + data["expires_in"] - 60

def run():
    config = load_config()
    load_env()
    logger = setup_logger("w1")
    auth = RedditAuth()
    conn = get_conn()
    topic = config["topic"]

    # Get active subreddits: prioritize queue_reparse, then least recently parsed
    subs = conn.execute("""
        SELECT name FROM subreddits
        WHERE active=1 AND topic=?
        ORDER BY queue_reparse DESC, last_parsed_at ASC NULLS FIRST, weight DESC
    """, (topic,)).fetchall()

    api_calls = 0
    total_posts = 0
    ua = os.environ["REDDIT_USER_AGENT"]

    for sub_row in subs:
        sub = sub_row["name"]
        if api_calls >= 580:
            logger.info("W1: API limit approaching, stopping")
            break

        try:
            headers = {"Authorization": f"Bearer {auth.get_token()}", "User-Agent": ua}
            resp = httpx.get(
                f"https://oauth.reddit.com/r/{sub}/top.json?t=week&limit={config['reddit_posts_per_request']}",
                headers=headers, timeout=15
            )
            api_calls += 1
            resp.raise_for_status()
            posts = resp.json()["data"]["children"]

            for post_data in posts:
                p = post_data["data"]
                if p.get("promoted"):
                    continue
                if p.get("ups", 0) < config["min_upvotes"]:
                    continue

                # Fetch top comments
                comments_json = None
                try:
                    cresp = httpx.get(
                        f"https://oauth.reddit.com/r/{sub}/comments/{p['id']}.json?limit=10&sort=top&depth=1",
                        headers=headers, timeout=15
                    )
                    api_calls += 1
                    cresp.raise_for_status()
                    comment_listing = cresp.json()
                    if len(comment_listing) > 1:
                        comments = [
                            c["data"].get("body", "")
                            for c in comment_listing[1]["data"]["children"]
                            if c["kind"] == "t1"
                        ]
                        comments_json = json.dumps(comments[:10])
                except Exception as e:
                    logger.warning(f"W1: failed to fetch comments for {p['id']}: {e}")

                if api_calls >= 580:
                    break

                try:
                    conn.execute("""
                        INSERT OR IGNORE INTO raw_posts (reddit_id, subreddit, title, body, url, upvotes, comments_json)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (p["id"], sub, p.get("title", ""), p.get("selftext", ""),
                          f"https://reddit.com{p.get('permalink', '')}", p.get("ups", 0), comments_json))
                    total_posts += 1
                except Exception as e:
                    logger.warning(f"W1: insert failed for {p['id']}: {e}")

            conn.execute("UPDATE subreddits SET last_parsed_at=?, queue_reparse=0 WHERE name=?",
                         (datetime.utcnow().isoformat(), sub))
            conn.commit()

        except Exception as e:
            logger.error(f"W1: error parsing r/{sub}: {e}")
            continue

    conn.commit()
    conn.close()
    logger.info(f"W1: parsed {total_posts} posts from {len(subs)} subreddits, {api_calls} API calls")

if __name__ == "__main__":
    run()
```

**Step 2: Test W1**

Run: `python -m workers.w1_parser`
Expected: Posts inserted into raw_posts. Check:
`python -c "from workers.db import get_conn; c=get_conn(); print(c.execute('SELECT COUNT(*) FROM raw_posts').fetchone()[0], 'posts')"`

**Step 3: Commit**

```bash
git add workers/w1_parser.py
git commit -m "feat: W1 Reddit parser — fetches top posts with OAuth2 and rate limiting"
```

---

### Task 4: W2 — Analyzer (workers/w2_analyzer.py)

**Files:**
- Create: `workers/w2_analyzer.py`

**Step 1: Create workers/w2_analyzer.py**

```python
import json
import asyncio
from workers.helpers import load_config, load_env, setup_logger, claude_call
from workers.db import get_conn

def build_batch_prompt(posts):
    batch = []
    for p in posts:
        item = {"post_id": p["id"], "title": p["title"], "body": (p["body"] or "")[:500]}
        if p["comments_json"]:
            try:
                item["top_comments"] = json.loads(p["comments_json"])[:5]
            except json.JSONDecodeError:
                pass
        batch.append(item)

    return f"""You analyze Reddit posts to find business opportunities.
For each post, extract ONLY specific user pain points —
things that don't work, that frustrate people, that they want improved.
Ignore vague complaints without specifics and positive posts.

Posts (JSON):
{json.dumps(batch, ensure_ascii=False)}

Return ONLY JSON, no markdown:
[{{"post_id": 123, "problems": ["pain 1", "pain 2"]}}]
If no problems — return empty problems array for that post."""

async def process_batch(batch_posts, config, logger):
    prompt = build_batch_prompt(batch_posts)
    raw = claude_call("claude-haiku-4-5-20250901", prompt, config, logger)
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
    return json.loads(raw)

def run():
    config = load_config()
    load_env()
    logger = setup_logger("w2")
    conn = get_conn()

    posts = conn.execute("""
        SELECT id, title, body, comments_json, subreddit, upvotes, url
        FROM raw_posts WHERE processed=0 ORDER BY upvotes DESC
    """).fetchall()

    if not posts:
        logger.info("W2: no unprocessed posts")
        return

    posts = [dict(p) for p in posts]
    batch_size = config["claude_batch_size"]
    batches = [posts[i:i+batch_size] for i in range(0, len(posts), batch_size)]

    total_problems = 0

    # Process up to 5 batches concurrently
    for chunk_start in range(0, len(batches), 5):
        chunk = batches[chunk_start:chunk_start+5]

        async def _run_chunk():
            tasks = [process_batch(b, config, logger) for b in chunk]
            return await asyncio.gather(*tasks, return_exceptions=True)

        results = asyncio.run(_run_chunk())

        for batch_posts, result in zip(chunk, results):
            if isinstance(result, Exception):
                logger.error(f"W2: batch failed: {result}")
                continue

            post_map = {p["id"]: p for p in batch_posts}
            for item in result:
                post = post_map.get(item["post_id"])
                if not post:
                    continue
                for problem_text in item.get("problems", []):
                    conn.execute("""
                        INSERT INTO problems (raw_post_id, subreddit, problem, upvotes, source_url)
                        VALUES (?, ?, ?, ?, ?)
                    """, (post["id"], post["subreddit"], problem_text, post["upvotes"], post["url"]))
                    total_problems += 1

            batch_ids = [p["id"] for p in batch_posts]
            conn.executemany("UPDATE raw_posts SET processed=1 WHERE id=?", [(pid,) for pid in batch_ids])
            conn.commit()

    conn.close()
    logger.info(f"W2: extracted {total_problems} problems from {len(posts)} posts")

if __name__ == "__main__":
    run()
```

**Step 2: Test W2**

Run: `python -m workers.w2_analyzer`
Expected: Problems extracted. Check:
`python -c "from workers.db import get_conn; c=get_conn(); print(c.execute('SELECT COUNT(*) FROM problems').fetchone()[0], 'problems')"`

**Step 3: Commit**

```bash
git add workers/w2_analyzer.py
git commit -m "feat: W2 analyzer — extracts pain points via Claude Haiku batches"
```

---

### Task 5: W3 — Digest + Telegram (workers/w3_digest.py)

**Files:**
- Create: `workers/w3_digest.py`

**Step 1: Create workers/w3_digest.py**

```python
import json
import os
import httpx
from datetime import datetime
from workers.helpers import load_config, load_env, setup_logger, claude_call, ROOT
from workers.db import get_conn

def is_duplicate(new_title, existing_titles, threshold):
    new_words = set(w for w in new_title.lower().split() if len(w) > 4)
    if not new_words:
        return False
    for existing in existing_titles:
        ex_words = set(w for w in existing.lower().split() if len(w) > 4)
        overlap = len(new_words & ex_words) / len(new_words)
        if overlap >= threshold:
            return True
    return False

def send_telegram(message, logger):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        logger.warning("W3: Telegram credentials not configured, skipping send")
        return False
    try:
        resp = httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"},
            timeout=15
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"W3: Telegram send failed: {e}")
        return False

def run():
    config = load_config()
    load_env()
    logger = setup_logger("w3")
    conn = get_conn()
    topic = config["topic"]

    # Get recent problems
    problems = conn.execute("""
        SELECT problem, subreddit, upvotes, source_url
        FROM problems
        WHERE parsed_at >= datetime('now', '-7 days')
        ORDER BY upvotes DESC
        LIMIT 200
    """).fetchall()

    if not problems:
        logger.info("W3: no recent problems found")
        return

    problems_list = "\n".join(
        f"- {p['problem']} | r/{p['subreddit']} | ↑{p['upvotes']} | {p['source_url']}"
        for p in problems
    )

    prompt = f"""You are an expert at finding business ideas. You analyze real Reddit user pain points.
Research topic: {topic}

User pain points:
{problems_list}

Find product ideas that solve these pains. Be strict with scoring:
score 9-10 only for truly outstanding ideas with large market potential.
Minimum {config['digest_min_ideas']} ideas even if scores are below threshold.
Include ALL ideas with score >= {config['idea_score_threshold']}.

Return ONLY JSON, no markdown:
[{{
  "title": "name",
  "description": "2-3 sentences: what pain, what solution",
  "product_example": "specifically what the product would look like",
  "score": 8,
  "market_score": 7,
  "difficulty_score": 4,
  "uniqueness_score": 8,
  "source_subreddits": ["subreddit1", "subreddit2"],
  "source_urls": ["url1", "url2"]
}}]"""

    raw = claude_call("claude-sonnet-4-6-20250514", prompt, config, logger)
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
    ideas = json.loads(raw)

    # Deduplication against last 30 days
    existing = conn.execute("""
        SELECT title FROM ideas WHERE created_at >= datetime('now', '-30 days')
    """).fetchall()
    existing_titles = [r["title"] for r in existing]

    saved_ideas = []
    for idea in ideas:
        dup = is_duplicate(idea["title"], existing_titles, config["idea_dedup_similarity_threshold"])
        conn.execute("""
            INSERT INTO ideas (topic, title, description, product_example, score,
                             market_score, difficulty_score, uniqueness_score,
                             source_urls, subreddits, is_duplicate)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (topic, idea["title"], idea["description"], idea["product_example"],
              idea["score"], idea["market_score"], idea["difficulty_score"],
              idea["uniqueness_score"], json.dumps(idea.get("source_urls", [])),
              json.dumps(idea.get("source_subreddits", [])), 1 if dup else 0))

        if not dup:
            saved_ideas.append(idea)
            # Update subreddit weights
            for sub_name in idea.get("source_subreddits", []):
                conn.execute("""
                    UPDATE subreddits SET weight = weight + ?, total_ideas = total_ideas + 1
                    WHERE name = ?
                """, (idea["score"] * 0.1, sub_name))

        existing_titles.append(idea["title"])

    # Save digest
    conn.execute("INSERT INTO digests (topic, ideas_json) VALUES (?, ?)",
                 (topic, json.dumps([i for i in saved_ideas], ensure_ascii=False)))
    conn.commit()

    # Telegram message
    if saved_ideas:
        lines = [f"🔍 Дайджест: {topic}", f"📅 {datetime.now().strftime('%Y-%m-%d')}", f"💡 Найдено идей: {len(saved_ideas)}", "", "━━━━━━━━━━━━━━━"]
        for idea in saved_ideas:
            lines.append(f"⭐ {idea['score']}/10  {idea['title']}")
            lines.append(idea["description"])
            lines.append(f"→ {idea['product_example']}")
            lines.append(f"📊 Рынок {idea['market_score']}/10 · Сложность {idea['difficulty_score']}/10 · Уникальность {idea['uniqueness_score']}/10")
            lines.append(f"📌 Источники: {', '.join(idea.get('source_subreddits', []))}")
            lines.append("━━━━━━━━━━━━━━━")
        msg = "\n".join(lines)
        if send_telegram(msg, logger):
            conn.execute("UPDATE digests SET sent_to_tg=1 WHERE id=(SELECT MAX(id) FROM digests)")
            conn.commit()

    conn.close()
    logger.info(f"W3: generated {len(saved_ideas)} ideas, {len(ideas) - len(saved_ideas)} duplicates skipped")

if __name__ == "__main__":
    run()
```

**Step 2: Test W3**

Run: `python -m workers.w3_digest`
Expected: Ideas in DB, digest saved. Check:
`python -c "from workers.db import get_conn; c=get_conn(); [print(dict(r)) for r in c.execute('SELECT title, score FROM ideas ORDER BY score DESC LIMIT 5')]"`

**Step 3: Commit**

```bash
git add workers/w3_digest.py
git commit -m "feat: W3 digest — generates ideas via Claude Sonnet + Telegram delivery"
```

---

### Task 6: W4 — Reparse Suggestions (workers/w4_reparse.py)

**Files:**
- Create: `workers/w4_reparse.py`

**Step 1: Create workers/w4_reparse.py**

```python
import os
import httpx
from workers.helpers import load_config, load_env, setup_logger
from workers.db import get_conn

def send_telegram(message, logger):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        logger.warning("W4: Telegram not configured")
        return False
    try:
        resp = httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"},
            timeout=15
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"W4: Telegram failed: {e}")
        return False

def run():
    config = load_config()
    load_env()
    logger = setup_logger("w4")
    conn = get_conn()

    subs = conn.execute("""
        SELECT name, total_ideas FROM subreddits
        WHERE total_ideas > 0
        AND last_parsed_at <= datetime('now', ? || ' days')
        AND queue_reparse = 0 AND active = 1
    """, (f"-{config['reparse_days']}",)).fetchall()

    sent = 0
    for sub in subs:
        top_idea = conn.execute("""
            SELECT title, score FROM ideas
            WHERE subreddits LIKE ? ORDER BY score DESC LIMIT 1
        """, (f'%{sub["name"]}%',)).fetchone()

        if top_idea:
            msg = (f"📌 Пора перепарсить: r/{sub['name']}\n"
                   f"Неделю назад здесь нашли {sub['total_ideas']} идей\n"
                   f"Лучшая: {top_idea['title']} (⭐{top_idea['score']})\n"
                   f"Добавить в очередь? → /reparse_{sub['name']}")
            if send_telegram(msg, logger):
                sent += 1

    conn.close()
    logger.info(f"W4: sent {sent} reparse reminders")

if __name__ == "__main__":
    run()
```

**Step 2: Commit**

```bash
git add workers/w4_reparse.py
git commit -m "feat: W4 reparse suggestions — notifies about stale subreddits via Telegram"
```

---

### Task 7: run_all.py — Cold Start Runner

**Files:**
- Create: `workers/run_all.py`

**Step 1: Create workers/run_all.py**

```python
import time
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from workers.helpers import setup_logger
from workers.db import init_db
from workers import w0_topic, w1_parser, w2_analyzer, w3_digest

def run():
    logger = setup_logger("run_all")
    logger.info("=== Cold start: running full pipeline ===")

    init_db()

    steps = [
        ("W0 topic", lambda: w0_topic.run(force=True)),
        ("W1 parser", lambda: w1_parser.run()),
        ("W2 analyzer", lambda: w2_analyzer.run()),
        ("W3 digest", lambda: w3_digest.run()),
    ]

    for name, fn in steps:
        logger.info(f"Starting {name}...")
        start = time.time()
        try:
            fn()
        except Exception as e:
            logger.error(f"{name} failed: {e}")
            raise
        elapsed = time.time() - start
        logger.info(f"{name} completed in {elapsed:.1f}s")
        time.sleep(2)

    logger.info("=== Cold start complete ===")

if __name__ == "__main__":
    run()
```

**Step 2: Commit**

```bash
git add workers/run_all.py
git commit -m "feat: run_all.py — cold start runner for full pipeline"
```

---

### Task 8: FastAPI (api/main.py)

**Files:**
- Create: `api/main.py`

**Step 1: Create api/main.py**

Full FastAPI app with all endpoints:
- GET/POST /api/config
- GET /api/ideas (with filters)
- POST /api/ideas/{id}/favourite
- GET /api/subreddits
- POST /api/subreddits/{name}/queue
- GET /api/digests
- GET /api/stats
- POST /api/workers/run/{worker}

CORS for localhost:3000. SQLite WAL in startup. Background task for W0 on topic change. Subprocess launch for worker runs.

**Step 2: Test API**

Run: `uvicorn api.main:app --reload --port 8000`
Then: `curl http://localhost:8000/api/stats`
Expected: JSON with counts

**Step 3: Commit**

```bash
git add api/main.py
git commit -m "feat: FastAPI REST API with all endpoints"
```

---

### Task 9: React Frontend — Scaffold

**Files:**
- Create: Vite project in `frontend/`
- Configure: Tailwind, proxy, React Router

**Step 1: Scaffold Vite + React + TS**

```bash
cd frontend
npm create vite@latest . -- --template react-ts
npm install tailwindcss @tailwindcss/vite recharts react-router-dom
```

**Step 2: Configure vite.config.ts with API proxy**

**Step 3: Set up Tailwind, router, layout**

**Step 4: Commit**

```bash
git add frontend/
git commit -m "feat: React frontend scaffold with Vite + Tailwind + Router"
```

---

### Task 10: Frontend — Daily.tsx

**Files:**
- Create: `frontend/src/pages/Daily.tsx`
- Create: `frontend/src/components/IdeaCard.tsx`
- Create: `frontend/src/components/BubbleChart.tsx`

Features: Date picker, bubble/list toggle, idea cards with favourite toggle, worker control panel.

**Step 1: Build components**

**Step 2: Test in browser**

**Step 3: Commit**

---

### Task 11: Frontend — Trends.tsx

**Files:**
- Create: `frontend/src/pages/Trends.tsx`

Features: Line chart (ideas/day, 30 days), bar chart (top-10 subreddits by weight), top-5 ideas table.

---

### Task 12: Frontend — Ideas.tsx

**Files:**
- Create: `frontend/src/pages/Ideas.tsx`

Features: Filterable idea list (70%), subreddit panel (30%) with queue buttons, pagination.

---

### Task 13: setup.sh + final integration

**Files:**
- Create: `setup.sh`
- Update: `CLAUDE.md` (all checkboxes done)
- Update: `.gitignore` if needed

**Step 1: Create setup.sh**

Installs Python deps, npm deps, inits DB, sets up cron jobs.

**Step 2: Final commit + push**

```bash
git add -A
git commit -m "feat: setup.sh and final integration"
git push origin main
```
