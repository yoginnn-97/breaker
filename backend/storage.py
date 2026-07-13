"""
Thin shim that keeps the same function signatures as the old CSV/JSON
storage layer but delegates all persistence to backend.db (SQLite).
"""
from datetime import date, datetime
from . import db


def _ensure(username):
    db.init_db(username)


# ── sessions ──────────────────────────────────────────────────────────────────

def save_session(category, task, start_dt, end_dt, username):
    _ensure(username)
    db.save_session(username, category, task, start_dt, end_dt)


def load_all(username):
    """Returns list of row dicts or None if empty."""
    _ensure(username)
    rows = db.load_all_sessions(username)
    return rows if rows else None


def load_for_date(target_date, username):
    """Returns list of row dicts for the given date, or None if empty."""
    _ensure(username)
    rows = db.load_sessions_for_date(username, target_date)
    return rows if rows else None


def clear_all(username):
    _ensure(username)
    db.clear_sessions(username)


# ── active session ────────────────────────────────────────────────────────────

def start_active_session(category, task, username):
    _ensure(username)
    db.start_active_session(username, category, task)


def get_active_session(username):
    _ensure(username)
    return db.get_active_session(username)


def clear_active_session(username):
    _ensure(username)
    db.clear_active_session(username)
