from datetime import date, timedelta

import pandas as pd


def day_stats(day_df, goal):
    """Total minutes, goal progress (0-1), and session count for a single day."""
    if day_df is None or day_df.empty:
        return {"total": 0, "progress": 0.0, "sessions": 0}
    total = round(day_df["Duration_Min"].sum(), 1)
    progress = min(total / goal, 1.0) if goal > 0 else 0.0
    return {"total": total, "progress": progress, "sessions": len(day_df)}


def weekly_trend(all_df, days=7):
    """Total minutes per day for the last N days (including today), oldest first."""
    today = date.today()
    day_range = [today - timedelta(days=i) for i in range(days - 1, -1, -1)]

    if all_df is None or all_df.empty:
        totals = {d: 0 for d in day_range}
    else:
        by_day = all_df.groupby(all_df["Date"].dt.date)["Duration_Min"].sum()
        totals = {d: int(by_day.get(d, 0)) for d in day_range}

    return pd.DataFrame(
        {
            "Day": [d.strftime("%a %d") for d in totals.keys()],
            "Minutes": list(totals.values()),
        }
    )


def category_totals(all_df, days=None):
    """Minutes per category, optionally restricted to the last `days` days."""
    if all_df is None or all_df.empty:
        return pd.DataFrame(columns=["Category", "Minutes"])

    df = all_df
    if days is not None:
        cutoff = date.today() - timedelta(days=days - 1)
        df = df[df["Date"].dt.date >= cutoff]

    if df.empty:
        return pd.DataFrame(columns=["Category", "Minutes"])

    totals = df.groupby("Category")["Duration_Min"].sum().reset_index()
    totals.columns = ["Category", "Minutes"]
    return totals.sort_values("Minutes", ascending=False)


def current_streak(all_df):
    """Consecutive days up to and including today with at least one logged session."""
    if all_df is None or all_df.empty:
        return 0
    logged_days = set(all_df["Date"].dt.date.unique())
    streak = 0
    cursor = date.today()
    while cursor in logged_days:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def session_extremes(all_df):
    """Longest and average session length in minutes, across all logged sessions."""
    if all_df is None or all_df.empty:
        return {"longest": 0, "average": 0}
    return {
        "longest": int(all_df["Duration_Min"].max()),
        "average": int(round(all_df["Duration_Min"].mean())),
    }


def build_journal(day_df, target_date, goal):
    """
    Builds a journal entry for one day.
    Returns (markdown_text, html_card) or (None, None) if there's nothing to summarize.
    """
    if day_df is None or day_df.empty:
        return None, None

    total = int(day_df["Duration_Min"].sum())
    progress = min(total / goal, 1.0) if goal > 0 else 0.0
    sessions = len(day_df)
    suffix = "s" if sessions != 1 else ""

    md = f"## Daily Log: {target_date.strftime('%B %d, %Y')}\n\n"
    md += f"**Total time:** {total} minutes across {sessions} session{suffix}.\n\n"
    md += f"**Goal progress:** {int(progress * 100)}% of {goal}-minute goal.\n\n"
    md += "### Tasks\n"

    lines_html = ""
    for _, row in day_df.iterrows():
        c = str(row["Category"])
        t = str(row["Task"])
        d = int(row["Duration_Min"])
        display_task = t if t.lower() != c.lower() else c
        md += f"- **[{c}]** {display_task} ({d} mins)\n"
        lines_html += f'<div class="line-item">[<b>{c}</b>] {display_task} — {d} min</div>'

    html = f"""
    <div class="journal-card">
        On {target_date.strftime('%B %d, %Y')} you spent <b>{total} minutes</b> across
        {sessions} session{suffix}, reaching <b>{int(progress * 100)}%</b> of your
        {goal}-minute goal.
        {lines_html}
    </div>
    """
    return md, html
