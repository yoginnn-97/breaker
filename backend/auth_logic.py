import hashlib
import hmac
import json
import os

from .constants import ACCOUNTS_FILE

# Default used only for local dev when nothing else is configured, so the
# app doesn't crash the first time you run it. Anything deployed publicly
# should override this via the BREAKER_SIGNUP_KEY environment variable.
_FALLBACK_DEV_KEY = "changeme"


def signup_key():
    """Resolves the current invite key: BREAKER_SIGNUP_KEY env var if set,
    otherwise a hardcoded local-dev fallback (never rely on this in a
    real deployment)."""
    env_key = os.environ.get("BREAKER_SIGNUP_KEY")
    if env_key:
        return env_key
    return _FALLBACK_DEV_KEY


def using_fallback_key():
    return signup_key() == _FALLBACK_DEV_KEY


def _hash(password, salt=None):
    """Salted PBKDF2-HMAC-SHA256, stored as 'salt_hex$hash_hex'."""
    if salt is None:
        salt = os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 200_000)
    return f"{salt}${digest.hex()}"


def _verify_password(password, stored):
    """Returns (is_correct, is_legacy_format); legacy bare-SHA256 accounts
    still verify and get upgraded automatically on next successful login."""
    if "$" not in stored:
        legacy_hash = hashlib.sha256(password.encode()).hexdigest()
        return hmac.compare_digest(legacy_hash, stored), True
    salt, _, hex_digest = stored.partition("$")
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 200_000)
    return hmac.compare_digest(digest.hex(), hex_digest), False


def _static_users():
    """Admin-provisioned accounts via BREAKER_USERS env var, formatted as
    'user1:pass1,user2:pass2'. These are meant to survive redeploys since
    they don't live in a file that could get wiped."""
    raw = os.environ.get("BREAKER_USERS", "")
    users = {}
    for pair in raw.split(","):
        if ":" in pair:
            u, p = pair.split(":", 1)
            users[u.strip()] = p.strip()
    return users


def _load_accounts():
    """Self-signed-up accounts: {username: password_hash}."""
    if not os.path.exists(ACCOUNTS_FILE):
        return {}
    try:
        with open(ACCOUNTS_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_accounts(accounts):
    os.makedirs(os.path.dirname(ACCOUNTS_FILE), exist_ok=True)
    with open(ACCOUNTS_FILE, "w") as f:
        json.dump(accounts, f, indent=2)


def all_usernames():
    return set(_static_users()) | set(_load_accounts())


def check_password(username, password):
    static = _static_users()
    if username in static:
        return hmac.compare_digest(str(static[username]), password)

    accounts = _load_accounts()
    if username not in accounts:
        return False

    is_correct, is_legacy = _verify_password(password, accounts[username])
    if is_correct and is_legacy:
        accounts[username] = _hash(password)
        _save_accounts(accounts)
    return is_correct


def create_account(username, password, key):
    """Returns (ok: bool, message: str)."""
    if not hmac.compare_digest(key, signup_key()):
        return False, "Wrong access key."
    if not username or not password:
        return False, "Username and password can't be empty."
    if username in all_usernames():
        return False, "That username is already taken."
    accounts = _load_accounts()
    accounts[username] = _hash(password)
    _save_accounts(accounts)
    return True, "Account created!"
