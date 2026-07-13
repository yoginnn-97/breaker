"""Thin shim over db.py keeping the same function signatures."""
from . import db


def load_categories(username):
    db.init_db(username)
    return db.load_categories(username)


def save_categories(categories, username):
    db.init_db(username)
    db.save_categories(username, categories)


def load_settings(username):
    db.init_db(username)
    return db.load_settings(username)


def save_settings(settings, username):
    db.init_db(username)
    db.save_settings(username, settings)
