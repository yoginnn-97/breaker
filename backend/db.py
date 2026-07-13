"""
SQLite persistence layer for Breaker.

One database file per user: data/<username>/breaker.db
Tables:
  sessions  — every logged session
  settings  — key/value app settings (daily_goal, etc.)
  categories — ordered list of category names
  active_session — at most one row: the currently running session

This replaces the CSV + JSON + active_session.json approach, which was
fragile (CSV appends, JSON overwrites, no transactions, no schema).
"""
import sqlite3
import json
import os
from datetime import datetime
from contextlib import contextmanager

from .constants import user_dir


def _db_path(username: str) -> str:
    return os.path.join(user_dir(username), "breaker.db")


@contextmanager
def _conn(username: str):
    path = _db_path(username)
    conn = sqlite3.connect(path, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")   # safe concurrent reads
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(username: str):
    """Create tables if they don't exist yet. Call once on first login."""
    with _conn(username) as c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                date         TEXT    NOT NULL,
                category     TEXT    NOT NULL,
                task         TEXT    NOT NULL,
                start_time   TEXT    NOT NULL,
                end_time     TEXT    NOT NULL,
                duration_min REAL    NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_sessions_date ON sessions(date);

            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS categories (
                position INTEGER PRIMARY KEY AUTOINCREMENT,
                name     TEXT    NOT NULL UNIQUE
            );

            CREATE TABLE IF NOT EXISTS active_session (
                id         INTEGER PRIMARY KEY CHECK (id = 1),
                category   TEXT    NOT NULL,
                task       TEXT    NOT NULL,
                start_time TEXT    NOT NULL
            );
        """)


# ── sessions ──────────────────────────────────────────────────────────────────

def save_session(username, category, task, start_dt, end_dt):
    task = task or category
    secs = (end_dt - start_dt).total_seconds()
    dur  = max(round(secs / 60, 2), 0.02)
    with _conn(username) as c:
        c.execute("""
            INSERT INTO sessions (date, category, task, start_time, end_time, duration_min)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            start_dt.strftime("%Y-%m-%d"),
            category, task,
            start_dt.strftime("%H:%M"),
            end_dt.strftime("%H:%M"),
            dur,
        ))


def load_all_sessions(username):
    """Returns list of dicts, newest first."""
    with _conn(username) as c:
        rows = c.execute(
            "SELECT * FROM sessions ORDER BY date DESC, start_time DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def load_sessions_for_date(username, target_date):
    date_str = target_date.strftime("%Y-%m-%d")
    with _conn(username) as c:
        rows = c.execute(
            "SELECT * FROM sessions WHERE date = ? ORDER BY start_time",
            (date_str,)
        ).fetchall()
    return [dict(r) for r in rows]


def clear_sessions(username):
    with _conn(username) as c:
        c.execute("DELETE FROM sessions")


# ── active session ────────────────────────────────────────────────────────────

def start_active_session(username, category, task):
    with _conn(username) as c:
        c.execute("""
            INSERT OR REPLACE INTO active_session (id, category, task, start_time)
            VALUES (1, ?, ?, ?)
        """, (category, task or category, datetime.now().isoformat()))


def get_active_session(username):
    with _conn(username) as c:
        row = c.execute("SELECT * FROM active_session WHERE id = 1").fetchone()
    if row is None:
        return None
    d = dict(row)
    d["start_time"] = datetime.fromisoformat(d["start_time"])
    return d


def clear_active_session(username):
    with _conn(username) as c:
        c.execute("DELETE FROM active_session WHERE id = 1")


# ── categories ────────────────────────────────────────────────────────────────

_DEFAULT_CATEGORIES = ["Study", "Work", "Exercise", "Reading",
                       "Meditation", "Personal Projects"]


def load_categories(username):
    with _conn(username) as c:
        rows = c.execute(
            "SELECT name FROM categories ORDER BY position"
        ).fetchall()
    if rows:
        return [r["name"] for r in rows]
    # first use: seed from the root config.json if it exists, else use defaults
    from .constants import CONFIG_FILE
    import json, os
    cats = _DEFAULT_CATEGORIES
    if os.path.exists(CONFIG_FILE):
        try:
            cats = json.load(open(CONFIG_FILE)).get("categories", cats) or cats
        except Exception:
            pass
    save_categories(username, cats)
    return cats


def save_categories(username, categories):
    with _conn(username) as c:
        c.execute("DELETE FROM categories")
        c.executemany(
            "INSERT INTO categories (name) VALUES (?)",
            [(cat,) for cat in categories]
        )


# ── settings ──────────────────────────────────────────────────────────────────

_DEFAULT_SETTINGS = {"daily_goal": 240}


def load_settings(username):
    with _conn(username) as c:
        rows = c.execute("SELECT key, value FROM settings").fetchall()
    if not rows:
        s = dict(_DEFAULT_SETTINGS)
        save_settings(username, s)
        return s
    result = dict(_DEFAULT_SETTINGS)
    for r in rows:
        try:
            result[r["key"]] = json.loads(r["value"])
        except Exception:
            result[r["key"]] = r["value"]
    return result


def save_settings(username, settings):
    with _conn(username) as c:
        c.executemany(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            [(k, json.dumps(v)) for k, v in settings.items()]
        )
