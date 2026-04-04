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

        # Migrations — idempotent column additions
        try:
            conn.execute("ALTER TABLE raw_posts ADD COLUMN comments_fetched INTEGER DEFAULT 0")
            conn.commit()
        except Exception as e:
            if "duplicate column" not in str(e).lower():
                raise
