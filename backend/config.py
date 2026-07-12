import json
import os

from .constants import CONFIG_FILE, SETTINGS_FILE, user_config_file, user_settings_file

DEFAULT_CATEGORIES = ["Work"]
DEFAULT_SETTINGS = {"daily_goal": 240}


def _seed_categories():
    """First-login default: the repo's template config.json if present,
    otherwise a bare-bones fallback."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                cats = json.load(f).get("categories")
                if cats:
                    return cats
        except (json.JSONDecodeError, OSError):
            pass
    return DEFAULT_CATEGORIES


def _seed_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                return {**DEFAULT_SETTINGS, **json.load(f)}
        except (json.JSONDecodeError, OSError):
            pass
    return dict(DEFAULT_SETTINGS)


def load_categories(username):
    """Loads this user's categories, seeding from the template on first use."""
    path = user_config_file(username)
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                cats = json.load(f).get("categories", DEFAULT_CATEGORIES)
                return cats if cats else DEFAULT_CATEGORIES
        except (json.JSONDecodeError, OSError):
            return DEFAULT_CATEGORIES
    cats = _seed_categories()
    save_categories(cats, username)
    return cats


def save_categories(categories, username):
    with open(user_config_file(username), "w") as f:
        json.dump({"categories": categories}, f, indent=2)


def load_settings(username):
    """Loads this user's settings, seeding from the template on first use."""
    path = user_settings_file(username)
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                return {**DEFAULT_SETTINGS, **json.load(f)}
        except (json.JSONDecodeError, OSError):
            return dict(DEFAULT_SETTINGS)
    settings = _seed_settings()
    save_settings(settings, username)
    return settings


def save_settings(settings, username):
    with open(user_settings_file(username), "w") as f:
        json.dump(settings, f, indent=2)
