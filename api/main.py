import json
import subprocess
import sys
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from workers.db import get_conn, init_db
from workers.helpers import load_config, save_config, ROOT


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Reddit Miner API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/config")
def get_config():
    return load_config()


@app.post("/api/config")
async def update_config(body: dict):
    config = load_config()
    old_topic = config.get("topic")
    config.update(body)
    save_config(config)
    if body.get("topic") and body["topic"] != old_topic:
        subprocess.Popen(
            [sys.executable, "-m", "workers.w0_topic", "--force"],
            cwd=ROOT,
        )
    return config


@app.get("/api/ideas")
def get_ideas(
    date: str = None,
    topic: str = None,
    subreddit: str = None,
    favourite: int = None,
    min_score: float = None,
    show_duplicates: int = 0,
    limit: int = 50,
    offset: int = 0,
):
    conn = get_conn()
    query = "SELECT * FROM ideas WHERE 1=1"
    params = []

    if not show_duplicates:
        query += " AND is_duplicate=0"
    if date:
        query += " AND DATE(created_at)=?"
        params.append(date)
    if topic:
        query += " AND topic=?"
        params.append(topic)
    if subreddit:
        query += " AND subreddits LIKE ?"
        params.append(f"%{subreddit}%")
    if favourite is not None:
        query += " AND is_favourite=?"
        params.append(favourite)
    if min_score is not None:
        query += " AND score>=?"
        params.append(min_score)

    query += " ORDER BY score DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/api/ideas/{idea_id}/favourite")
def toggle_favourite(idea_id: int):
    conn = get_conn()
    idea = conn.execute("SELECT is_favourite, subreddits FROM ideas WHERE id=?", (idea_id,)).fetchone()
    if not idea:
        conn.close()
        return {"error": "not found"}

    new_val = 0 if idea["is_favourite"] else 1
    conn.execute("UPDATE ideas SET is_favourite=? WHERE id=?", (new_val, idea_id))

    if new_val == 1 and idea["subreddits"]:
        try:
            subs = json.loads(idea["subreddits"])
            for sub_name in subs:
                conn.execute(
                    "UPDATE subreddits SET weight = weight + 0.5 WHERE name=?",
                    (sub_name,),
                )
        except json.JSONDecodeError:
            pass

    conn.commit()
    conn.close()
    return {"id": idea_id, "is_favourite": new_val}


@app.get("/api/subreddits")
def get_subreddits(topic: str = None, active: int = None):
    conn = get_conn()
    query = "SELECT * FROM subreddits WHERE 1=1"
    params = []
    if topic:
        query += " AND topic=?"
        params.append(topic)
    if active is not None:
        query += " AND active=?"
        params.append(active)
    query += " ORDER BY weight DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/api/subreddits/{name}/queue")
def queue_subreddit(name: str):
    conn = get_conn()
    conn.execute("UPDATE subreddits SET queue_reparse=1 WHERE name=?", (name,))
    conn.commit()
    conn.close()
    return {"name": name, "queued": True}


@app.get("/api/digests")
def get_digests(limit: int = 30):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM digests ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/stats")
def get_stats():
    conn = get_conn()
    stats = {
        "total_ideas": conn.execute("SELECT COUNT(*) FROM ideas WHERE is_duplicate=0").fetchone()[0],
        "total_posts": conn.execute("SELECT COUNT(*) FROM raw_posts").fetchone()[0],
        "total_problems": conn.execute("SELECT COUNT(*) FROM problems").fetchone()[0],
        "total_subreddits": conn.execute("SELECT COUNT(*) FROM subreddits WHERE active=1").fetchone()[0],
        "last_run_at": conn.execute(
            "SELECT MAX(created_at) FROM digests"
        ).fetchone()[0],
    }
    conn.close()
    return stats


@app.post("/api/workers/run/{worker}")
def run_worker(worker: str):
    valid = {"w0", "w1", "w2", "w3", "w4", "all"}
    if worker not in valid:
        return {"error": f"invalid worker, use: {valid}"}

    if worker == "all":
        script = "workers.run_all"
    else:
        script = f"workers.{worker}_{'topic' if worker=='w0' else 'parser' if worker=='w1' else 'analyzer' if worker=='w2' else 'digest' if worker=='w3' else 'reparse'}"

    subprocess.Popen(
        [sys.executable, "-m", script],
        cwd=ROOT,
    )
    return {"worker": worker, "status": "started"}
