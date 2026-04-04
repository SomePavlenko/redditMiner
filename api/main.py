import json
import subprocess
import sys
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from workers.db import use_conn, init_db
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
            [sys.executable, "-m", "workers.s0_scout_subreddits", "--force"],
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
    with use_conn() as conn:
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
            params.append(f'%"{subreddit}"%')
        if favourite is not None:
            query += " AND is_favourite=?"
            params.append(favourite)
        if min_score is not None:
            query += " AND score>=?"
            params.append(min_score)

        query += " ORDER BY score DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


@app.post("/api/ideas/{idea_id}/favourite")
def toggle_favourite(idea_id: int):
    with use_conn() as conn:
        idea = conn.execute(
            "SELECT is_favourite, subreddits FROM ideas WHERE id=?", (idea_id,)
        ).fetchone()
        if not idea:
            raise HTTPException(status_code=404, detail="Idea not found")

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
        return {"id": idea_id, "is_favourite": new_val}


@app.post("/api/ideas/{idea_id}/deep-analysis")
async def run_deep_analysis(idea_id: int):
    from prompts import DEEP_ANALYSIS

    with use_conn() as conn:
        idea = conn.execute("SELECT * FROM ideas WHERE id=?", (idea_id,)).fetchone()
        if not idea:
            raise HTTPException(status_code=404, detail="Idea not found")
        if idea["deep_analysis_done"]:
            return {"id": idea_id, "status": "already_done", "result": idea["deep_analysis_result"]}

    config = load_config()
    from workers.helpers import load_env, claude_call
    load_env()

    prompt = DEEP_ANALYSIS.format(
        title=idea["title"] or "",
        pain=idea["pain"] or "",
        solution=idea["solution"] or "",
        where_we_meet_user=idea["where_we_meet_user"] or "",
        monetization=idea["monetization"] or "",
        competition_level=idea["competition_level"] or "",
        competition_note=idea["competition_note"] or "",
    )

    try:
        result = claude_call(config["claude_model_smart"], prompt, config, __import__("logging").getLogger("api"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Claude API error: {e}")

    with use_conn() as conn:
        conn.execute(
            "UPDATE ideas SET deep_analysis_done=1, deep_analysis_result=? WHERE id=?",
            (result, idea_id),
        )
        conn.commit()

    return {"id": idea_id, "status": "done", "result": result}


@app.get("/api/subreddits")
def get_subreddits(topic: str = None, active: int = None):
    with use_conn() as conn:
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
        return [dict(r) for r in rows]


@app.post("/api/subreddits/{name}/queue")
def queue_subreddit(name: str):
    with use_conn() as conn:
        conn.execute("UPDATE subreddits SET queue_reparse=1 WHERE name=?", (name,))
        conn.commit()
        return {"name": name, "queued": True}


@app.get("/api/clusters")
def get_clusters(topic: str = None):
    with use_conn() as conn:
        if topic:
            rows = conn.execute(
                "SELECT * FROM pain_clusters WHERE topic=? ORDER BY pain_score DESC", (topic,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM pain_clusters ORDER BY pain_score DESC").fetchall()
        return [dict(r) for r in rows]


@app.get("/api/problems")
def get_problems(cluster_id: int = None, subreddit: str = None, topic: str = None, limit: int = 100):
    with use_conn() as conn:
        query = "SELECT * FROM problems WHERE 1=1"
        params = []
        if topic:
            query += " AND topic=?"
            params.append(topic)
        if cluster_id is not None:
            query += " AND cluster_id=?"
            params.append(cluster_id)
        if subreddit:
            query += " AND subreddit=?"
            params.append(subreddit)
        query += " ORDER BY upvotes DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


@app.get("/api/digests")
def get_digests(limit: int = 30):
    with use_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM digests ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


@app.get("/api/topics")
def get_topics():
    """All topics that have data."""
    with use_conn() as conn:
        rows = conn.execute(
            """SELECT topic, COUNT(*) as ideas_count
            FROM ideas WHERE is_duplicate=0 AND topic != ''
            GROUP BY topic ORDER BY ideas_count DESC"""
        ).fetchall()
        return [dict(r) for r in rows]


@app.get("/api/stats")
def get_stats(topic: str = None):
    with use_conn() as conn:
        if topic:
            return {
                "topic": topic,
                "total_ideas": conn.execute("SELECT COUNT(*) FROM ideas WHERE is_duplicate=0 AND topic=?", (topic,)).fetchone()[0],
                "total_posts": conn.execute("SELECT COUNT(*) FROM raw_posts WHERE topic=?", (topic,)).fetchone()[0],
                "total_problems": conn.execute("SELECT COUNT(*) FROM problems WHERE topic=?", (topic,)).fetchone()[0],
                "total_clusters": conn.execute("SELECT COUNT(*) FROM pain_clusters WHERE topic=?", (topic,)).fetchone()[0],
                "total_subreddits": conn.execute("SELECT COUNT(*) FROM subreddits WHERE active=1 AND topic=?", (topic,)).fetchone()[0],
                "last_run_at": conn.execute("SELECT MAX(created_at) FROM ideas WHERE topic=?", (topic,)).fetchone()[0],
            }
        return {
            "total_ideas": conn.execute("SELECT COUNT(*) FROM ideas WHERE is_duplicate=0").fetchone()[0],
            "total_posts": conn.execute("SELECT COUNT(*) FROM raw_posts").fetchone()[0],
            "total_problems": conn.execute("SELECT COUNT(*) FROM problems").fetchone()[0],
            "total_clusters": conn.execute("SELECT COUNT(*) FROM pain_clusters").fetchone()[0],
            "total_subreddits": conn.execute("SELECT COUNT(*) FROM subreddits WHERE active=1").fetchone()[0],
            "last_run_at": conn.execute("SELECT MAX(created_at) FROM ideas").fetchone()[0],
        }


@app.get("/api/health")
def health():
    with use_conn() as conn:
        conn.execute("SELECT 1")
        return {"status": "ok"}


WORKER_SCRIPTS = {
    "s0": "workers.s0_scout_subreddits",
    "s1": "workers.s1_fetch_reddit",
    "s2": "workers.s2_prepare_batches",
    "s3": "workers.s3_save_problems",
    "s4": "workers.s4_cluster_problems",
    "s5": "workers.s5_generate_ideas",
    "s6": "workers.s6_reparse_check",
    "pipeline": "workers.run_pipeline",
}


@app.post("/api/workers/run/{worker}")
def run_worker(worker: str):
    script = WORKER_SCRIPTS.get(worker)
    if not script:
        raise HTTPException(status_code=400, detail=f"Invalid worker. Use: {list(WORKER_SCRIPTS.keys())}")

    subprocess.Popen(
        [sys.executable, "-m", script],
        cwd=ROOT,
    )
    return {"worker": worker, "status": "started"}


# ── Pipeline runs with persistent IDs ─────────────────────────────────────────

from fastapi.responses import StreamingResponse
import asyncio
from datetime import datetime as dt
import uuid

STAGES = [
    ("S0", "Разведка сабреддитов", "workers.s0_scout_subreddits"),
    ("S1", "Парсинг Reddit", "workers.s1_fetch_reddit"),
    ("S2", "Подготовка батчей", "workers.s2_prepare_batches"),
    ("S3", "Анализ болей (Claude Haiku)", "workers.s3_save_problems"),
    ("S4", "Кластеризация (Claude Haiku)", "workers.s4_cluster_problems"),
    ("S5", "Генерация идей (Claude)", "workers.s5_generate_ideas"),
]


def _build_summary(run_topic):
    with use_conn() as conn:
        return {
            "stats": {
                "posts": conn.execute("SELECT COUNT(*) FROM raw_posts WHERE topic=?", (run_topic,)).fetchone()[0],
                "problems": conn.execute("SELECT COUNT(*) FROM problems WHERE topic=?", (run_topic,)).fetchone()[0],
                "clusters": conn.execute("SELECT COUNT(*) FROM pain_clusters WHERE topic=?", (run_topic,)).fetchone()[0],
                "ideas": conn.execute("SELECT COUNT(*) FROM ideas WHERE is_duplicate=0 AND topic=?", (run_topic,)).fetchone()[0],
            },
            "top_ideas": [
                dict(r) for r in conn.execute(
                    """SELECT id, title, score, pain, competition_level, monetization, validation_step
                    FROM ideas WHERE topic=? AND is_duplicate=0
                    ORDER BY score DESC LIMIT 5""",
                    (run_topic,),
                ).fetchall()
            ],
            "top_clusters": [
                dict(r) for r in conn.execute(
                    """SELECT id, cluster_name, pain_score, frequency, summary
                    FROM pain_clusters WHERE topic=?
                    ORDER BY pain_score DESC LIMIT 5""",
                    (run_topic,),
                ).fetchall()
            ],
        }


@app.get("/api/runs")
def list_runs():
    with use_conn() as conn:
        rows = conn.execute(
            "SELECT id, topic, status, created_at FROM runs ORDER BY created_at DESC LIMIT 50"
        ).fetchall()
        return [dict(r) for r in rows]


@app.get("/api/run/{run_id}")
def get_run(run_id: str):
    with use_conn() as conn:
        row = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Run not found")
        result = dict(row)
        if result.get("logs_json"):
            result["logs"] = json.loads(result["logs_json"])
        if result.get("result_json"):
            result["result"] = json.loads(result["result_json"])
        if result.get("params_json"):
            result["params"] = json.loads(result["params_json"])
        return result


@app.get("/api/run/{run_id}/stream")
async def run_pipeline_stream(
    run_id: str,
    topic: str = None,
    min_upvotes: int = None,
    reddit_api_limit: int = None,
    posts_for_comments_n: int = None,
    claude_batch_size: int = None,
    body_max_chars: int = None,
):
    """Runs pipeline for given run_id, streams logs as SSE, persists to DB."""

    # Check if run exists and is not already done
    with use_conn() as conn:
        existing = conn.execute("SELECT status FROM runs WHERE id=?", (run_id,)).fetchone()
        if existing and existing["status"] != "pending":
            # Already running or done — just stream what we have
            run_data = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
            async def replay():
                logs = json.loads(run_data["logs_json"] or "[]")
                for log in logs:
                    yield f"data: {json.dumps(log, ensure_ascii=False)}\n\n"
                if run_data["result_json"]:
                    result = json.loads(run_data["result_json"])
                    result["type"] = "done"
                    yield f"data: {json.dumps(result, ensure_ascii=False)}\n\n"
            return StreamingResponse(replay(), media_type="text/event-stream")

    async def generate():
        import time
        all_logs = []

        # Apply overrides
        cfg = load_config()
        overrides = {}
        if topic:
            overrides["topic"] = topic
        if min_upvotes is not None:
            overrides["min_upvotes"] = min_upvotes
        if reddit_api_limit is not None:
            overrides["reddit_api_limit"] = reddit_api_limit
        if posts_for_comments_n is not None:
            overrides["posts_for_comments_n"] = posts_for_comments_n
        if claude_batch_size is not None:
            overrides["claude_batch_size"] = claude_batch_size
        if body_max_chars is not None:
            overrides["body_max_chars"] = body_max_chars

        if overrides:
            cfg.update(overrides)
            save_config(cfg)

        run_topic = cfg.get("topic", "")

        # Update run status
        with use_conn() as conn:
            conn.execute(
                "UPDATE runs SET status='running', topic=?, params_json=? WHERE id=?",
                (run_topic, json.dumps(overrides, ensure_ascii=False), run_id),
            )
            conn.commit()

        def emit(event):
            all_logs.append(event)
            return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

        if overrides:
            yield emit({"type": "log", "text": f"Параметры: {overrides}"})

        success = True
        failed_stage = None

        for stage_id, stage_name, module in STAGES:
            yield emit({"type": "stage_start", "stage": stage_id, "name": stage_name})

            start = time.time()
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-m", module,
                cwd=ROOT,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )

            async for line in proc.stdout:
                text = line.decode("utf-8", errors="replace").rstrip()
                if text:
                    yield emit({"type": "log", "stage": stage_id, "text": text})

            await proc.wait()
            elapsed = round(time.time() - start, 1)

            if proc.returncode != 0:
                yield emit({"type": "stage_error", "stage": stage_id, "elapsed": elapsed})
                success = False
                failed_stage = stage_id
                break
            else:
                yield emit({"type": "stage_done", "stage": stage_id, "elapsed": elapsed})

        # Build result
        if success:
            summary = _build_summary(run_topic)
            result = {"type": "done", "success": True, "topic": run_topic, **summary}
        else:
            result = {"type": "done", "success": False, "topic": run_topic, "failed_stage": failed_stage}

        yield f"data: {json.dumps(result, ensure_ascii=False)}\n\n"

        # Persist to DB
        with use_conn() as conn:
            conn.execute(
                "UPDATE runs SET status=?, logs_json=?, result_json=? WHERE id=?",
                (
                    "done" if success else "failed",
                    json.dumps(all_logs, ensure_ascii=False),
                    json.dumps(result, ensure_ascii=False),
                    run_id,
                ),
            )
            conn.commit()

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.post("/api/run/create")
def create_run():
    """Creates a new run with a unique ID."""
    run_id = dt.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
    with use_conn() as conn:
        conn.execute(
            "INSERT INTO runs (id, topic, status) VALUES (?, ?, 'pending')",
            (run_id, load_config().get("topic", "")),
        )
        conn.commit()
    return {"run_id": run_id}
