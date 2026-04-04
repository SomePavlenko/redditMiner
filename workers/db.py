import sqlite3
import os
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "miner.db")


def get_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def use_conn():
    """Context manager that ensures connection is always closed."""
    conn = get_conn()
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with use_conn() as conn:
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
          cluster_id INTEGER DEFAULT NULL,
          parsed_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS pain_clusters (
          id INTEGER PRIMARY KEY,
          topic TEXT NOT NULL,
          cluster_name TEXT,
          summary TEXT,
          problems_json TEXT,
          frequency INTEGER DEFAULT 0,
          total_upvotes INTEGER DEFAULT 0,
          avg_upvotes REAL DEFAULT 0,
          subreddit_spread INTEGER DEFAULT 0,
          subreddits_json TEXT,
          pain_score REAL DEFAULT 0,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS ideas (
          id INTEGER PRIMARY KEY,
          topic TEXT NOT NULL,
          title TEXT NOT NULL,
          description TEXT,
          product_example TEXT,
          revenue_model TEXT,
          score REAL DEFAULT 0,
          demand_score REAL DEFAULT 0,
          breadth_score REAL DEFAULT 0,
          feasibility_score REAL DEFAULT 0,
          uniqueness_score REAL DEFAULT 0,
          solves_clusters TEXT,
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

        # Migrations — idempotent column additions
        _migrate(conn, "raw_posts", "topic", "TEXT DEFAULT ''")
        _migrate(conn, "raw_posts", "comments_fetched", "INTEGER DEFAULT 0")
        _migrate(conn, "problems", "topic", "TEXT DEFAULT ''")
        _migrate(conn, "problems", "cluster_id", "INTEGER DEFAULT NULL")
        _migrate(conn, "ideas", "demand_score", "REAL DEFAULT 0")
        _migrate(conn, "ideas", "breadth_score", "REAL DEFAULT 0")
        _migrate(conn, "ideas", "feasibility_score", "REAL DEFAULT 0")
        _migrate(conn, "ideas", "revenue_model", "TEXT")
        _migrate(conn, "ideas", "solves_clusters", "TEXT")
        _migrate(conn, "ideas", "pain", "TEXT")
        _migrate(conn, "ideas", "solution", "TEXT")
        _migrate(conn, "ideas", "where_we_meet_user", "TEXT")
        _migrate(conn, "ideas", "monetization", "TEXT")
        _migrate(conn, "ideas", "monetization_type", "TEXT")
        _migrate(conn, "ideas", "competition_level", "TEXT")
        _migrate(conn, "ideas", "competition_note", "TEXT")
        _migrate(conn, "ideas", "validation_step", "TEXT")
        _migrate(conn, "ideas", "deep_analysis_done", "INTEGER DEFAULT 0")
        _migrate(conn, "ideas", "deep_analysis_result", "TEXT")
        _migrate(conn, "ideas", "feasibility_breakdown", "TEXT")
        _migrate(conn, "ideas", "reachability", "REAL DEFAULT 0")
        _migrate(conn, "ideas", "willingness_to_pay", "REAL DEFAULT 0")
        _migrate(conn, "ideas", "retention_potential", "REAL DEFAULT 0")

        # Runs table
        conn.execute("""
        CREATE TABLE IF NOT EXISTS runs (
          id TEXT PRIMARY KEY,
          topic TEXT NOT NULL,
          params_json TEXT,
          status TEXT DEFAULT 'running',
          logs_json TEXT DEFAULT '[]',
          result_json TEXT,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """)
        conn.commit()


def _migrate(conn, table, column, col_type):
    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
        conn.commit()
    except Exception as e:
        if "duplicate column" not in str(e).lower():
            raise
