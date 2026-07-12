import os
import re

# Project root = one level up from this backend/ folder, so paths work
# no matter what directory Streamlit is launched from.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Legacy single-tenant files — kept only as a seed template for brand-new
# accounts (so a first login still gets the nice default category list),
# and as the fallback storage when no login is configured (local dev).
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
SETTINGS_FILE = os.path.join(BASE_DIR, "settings.json")
DATA_FILE = os.path.join(BASE_DIR, "time_logs.csv")
ACTIVE_FILE = os.path.join(BASE_DIR, "active_session.json")

# Per-user storage — each logged-in account gets its own folder, so
# accounts never see or overwrite each other's data.
DATA_DIR = os.path.join(BASE_DIR, "data")


def _safe_slug(username):
    return re.sub(r"[^a-zA-Z0-9_-]", "_", username or "default") or "default"


def user_dir(username):
    d = os.path.join(DATA_DIR, _safe_slug(username))
    os.makedirs(d, exist_ok=True)
    return d


def user_config_file(username):
    return os.path.join(user_dir(username), "config.json")


def user_settings_file(username):
    return os.path.join(user_dir(username), "settings.json")


def user_data_file(username):
    return os.path.join(user_dir(username), "time_logs.csv")


def user_active_file(username):
    return os.path.join(user_dir(username), "active_session.json")


# Self-signed-up accounts live here as {username: password_hash}.
ACCOUNTS_FILE = os.path.join(DATA_DIR, "_accounts.json")


# Sunset palette, shared across every chart and category chip
# so a given category always reads as the same color everywhere in the app.
PALETTE = ["#F2A65A", "#E8896B", "#C97FB0", "#8F7FD1", "#F0C368", "#DE7A6E", "#B79FD1"]
