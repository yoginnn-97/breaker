"""
Analytics and journal functions.
Works with plain list-of-dicts from storage.py (SQLite rows),
no pandas dependency.
"""
from datetime import date, timedelta
from collections import defaultdict


def _rows(data):
    return data if data else []


def day_stats(rows, goal):
    if not rows:
        return {"total": 0, "progress": 0.0, "sessions": 0}
    total = round(sum(r["duration_min"] for r in rows), 1)
    progress = min(total / goal, 1.0) if goal > 0 else 0.0
    return {"total": total, "progress": progress, "sessions": len(rows)}


def weekly_trend(all_rows, days=7):
    today = date.today()
    day_range = [today - timedelta(days=i) for i in range(days - 1, -1, -1)]
    totals = {d: 0.0 for d in day_range}
    for r in _rows(all_rows):
        d = date.fromisoformat(r["date"]) if isinstance(r["date"], str) else r["date"]
        if d in totals:
            totals[d] += r["duration_min"]
    return [
        {"day": d.strftime("%a %d"), "minutes": round(totals[d], 1)}
        for d in day_range
    ]


def category_totals(all_rows, days=None):
    cutoff = (date.today() - timedelta(days=days - 1)) if days else None
    totals = defaultdict(float)
    for r in _rows(all_rows):
        d = date.fromisoformat(r["date"]) if isinstance(r["date"], str) else r["date"]
        if cutoff and d < cutoff:
            continue
        totals[r["category"]] += r["duration_min"]
    return sorted(
        [{"category": k, "minutes": round(v, 1)} for k, v in totals.items()],
        key=lambda x: x["minutes"], reverse=True
    )


def current_streak(all_rows):
    if not all_rows:
        return 0
    logged = set()
    for r in all_rows:
        d = date.fromisoformat(r["date"]) if isinstance(r["date"], str) else r["date"]
        logged.add(d)
    streak, cursor = 0, date.today()
    while cursor in logged:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def session_extremes(all_rows):
    if not all_rows:
        return {"longest": 0, "average": 0}
    durations = [r["duration_min"] for r in all_rows]
    return {
        "longest": round(max(durations), 1),
        "average": round(sum(durations) / len(durations), 1),
    }


def build_journal(rows, target_date, goal):
    if not rows:
        return None, None
    total    = round(sum(r["duration_min"] for r in rows), 1)
    progress = min(total / goal, 1.0) if goal > 0 else 0.0
    sessions = len(rows)
    suffix   = "s" if sessions != 1 else ""
    md  = f"## Daily Log: {target_date.strftime('%B %d, %Y')}\n\n"
    md += f"**Total time:** {total}m across {sessions} session{suffix}.\n\n"
    md += f"**Goal progress:** {int(progress * 100)}% of {goal}m goal.\n\n"
    md += "### Tasks\n"
    for r in rows:
        c, t, d = r["category"], r["task"], r["duration_min"]
        display = t if t.lower() != c.lower() else c
        md += f"- **[{c}]** {display} ({d}m)\n"
    return md, None
