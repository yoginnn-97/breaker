import json
import os
from datetime import datetime

import pandas as pd

from .constants import user_active_file, user_data_file


def save_session(category, task, start_dt, end_dt, username):
    """Appends one completed session to this user's CSV log. Returns the resolved task name."""
    data_file = user_data_file(username)
    duration_seconds = int((end_dt - start_dt).total_seconds())
    if duration_seconds < 1:
        duration_seconds = 1
    duration_minutes = round(duration_seconds / 60, 2)  # real minutes, not floored

    task_name = task if task else category

    new_row = pd.DataFrame(
        {
            "Date": [start_dt.strftime("%Y-%m-%d")],
            "Category": [category],
            "Task": [task_name],
            "Start": [start_dt.strftime("%H:%M")],
            "End": [end_dt.strftime("%H:%M")],
            "Duration_Min": [duration_minutes],
        }
    )

    if os.path.exists(data_file):
        df = pd.read_csv(data_file)
        df = pd.concat([df, new_row], ignore_index=True)
    else:
        df = new_row
    df.to_csv(data_file, index=False)
    return task_name


def load_all(username):
    """Returns this user's full session log as a DataFrame, or None if empty."""
    data_file = user_data_file(username)
    if not os.path.exists(data_file):
        return None
    df = pd.read_csv(data_file)
    if df.empty:
        return None
    df["Date"] = pd.to_datetime(df["Date"])
    df["Category"] = df["Category"].fillna("Work")
    df["Task"] = df["Task"].fillna(df["Category"])
    return df


def load_for_date(target_date, username):
    """Returns this user's sessions for a single date, or None if there are none."""
    df = load_all(username)
    if df is None:
        return None
    day_df = df[df["Date"].dt.date == target_date].copy()
    return day_df if not day_df.empty else None


def clear_all(username):
    """Deletes this user's entire session log. Irreversible."""
    data_file = user_data_file(username)
    if os.path.exists(data_file):
        os.remove(data_file)


def get_active_session(username):
    """Reads this user's in-progress session, if any. Shared across every
    device that user is signed into, since it's a per-user file rather
    than per-browser state."""
    active_file = user_active_file(username)
    if not os.path.exists(active_file):
        return None
    try:
        with open(active_file, "r") as f:
            data = json.load(f)
        data["start_time"] = datetime.fromisoformat(data["start_time"])
        return data
    except (json.JSONDecodeError, OSError, KeyError, ValueError):
        return None


def start_active_session(category, task, username):
    with open(user_active_file(username), "w") as f:
        json.dump({"category": category, "task": task, "start_time": datetime.now().isoformat()}, f)


def clear_active_session(username):
    active_file = user_active_file(username)
    if os.path.exists(active_file):
        os.remove(active_file)
