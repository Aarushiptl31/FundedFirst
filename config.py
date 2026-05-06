from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional


BASE_DIR = Path(__file__).resolve().parent


def _load_env_file() -> None:
    """Load environment variables from a local .env file."""
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)
    except Exception:
        return


try:
    from dotenv import load_dotenv  # type: ignore

    def load_env() -> None:
        load_dotenv(BASE_DIR / ".env")

except Exception:

    def load_env() -> None:  # type: ignore[no-redef]
        _load_env_file()


load_env()


def _clean_placeholder(value: Optional[str]) -> str:
    """Normalize environment values and drop obvious placeholders."""
    if value is None:
        return ""
    trimmed = value.strip()
    upper = trimmed.upper()
    placeholder_tokens = ("YOUR_", "REPLACE_ME", "PUT_", "ADD_")
    if any(upper.startswith(tok) for tok in placeholder_tokens) or "YOUR_" in upper:
        return ""
    return trimmed


def _get_env(key: str, default: Optional[str] = None) -> str:
    value = os.getenv(key, default)
    return _clean_placeholder(value)


def _get_float(key: str, default: float) -> float:
    raw = os.getenv(key)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _get_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


# ── Gemini AI ─────────────────────────────────────────────────────────────────
GEMINI_API_KEY: str = _get_env("GEMINI_API_KEY")
GEMINI_MODEL: str = _get_env("GEMINI_MODEL", "gemini-2.0-flash")
GEMINI_TEMPERATURE: float = _get_float("GEMINI_TEMPERATURE", 0.0)
GEMINI_TOP_P: float = _get_float("GEMINI_TOP_P", 0.1)
GEMINI_ENABLED: bool = bool(GEMINI_API_KEY)

# ── Firebase Admin (server-side) ──────────────────────────────────────────────
FIREBASE_CREDENTIALS_PATH: str = _get_env(
    "FIREBASE_CREDENTIALS_PATH", "firebase_credentials.json"
)

# ── Firebase Web (client-side Auth) ───────────────────────────────────────────
FIREBASE_WEB_API_KEY: str = _get_env("FIREBASE_WEB_API_KEY")
FIREBASE_AUTH_DOMAIN: str = _get_env("FIREBASE_AUTH_DOMAIN")
FIREBASE_PROJECT_ID: str = _get_env("FIREBASE_PROJECT_ID")
FIREBASE_STORAGE_BUCKET: str = _get_env("FIREBASE_STORAGE_BUCKET")
FIREBASE_MESSAGING_SENDER_ID: str = _get_env("FIREBASE_MESSAGING_SENDER_ID")
FIREBASE_APP_ID: str = _get_env("FIREBASE_APP_ID")

# ── Flask ─────────────────────────────────────────────────────────────────────
FLASK_SECRET_KEY: str = _get_env("FLASK_SECRET_KEY", "")

# ── Email ─────────────────────────────────────────────────────────────────────
EMAIL_USER: str = _get_env("EMAIL_USER")
EMAIL_PASSWORD: str = _get_env("EMAIL_PASSWORD")
RECIPIENT_EMAIL: str = _get_env("RECIPIENT_EMAIL")
EMAIL_SMTP: str = _get_env("EMAIL_SMTP", "smtp.gmail.com")
EMAIL_PORT: int = _get_int("EMAIL_PORT", 587)

# ── Telegram ──────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN: str = _get_env("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID: str = _get_env("TELEGRAM_CHAT_ID")

# ── CV PDF path (per-user now stored in Firestore; this is a local fallback) ──
CV_PDF_PATH: str = _get_env("CV_PDF_PATH", "")

# ── Finance and thresholds ────────────────────────────────────────────────────
USD_TO_INR_RATE: float = _get_float("USD_TO_INR_RATE", 84.0)
MIN_FUNDING_INR: float = _get_float("MIN_FUNDING_INR", 10_000_000.0)
REQUEST_DELAY: float = _get_float("REQUEST_DELAY", 2.0)
REQUEST_TIMEOUT: float = 20.0
HIGH_SCORE_THRESHOLD: int = _get_int("HIGH_SCORE_THRESHOLD", 30)
ALERT_SCORE_THRESHOLD: int = _get_int("ALERT_SCORE_THRESHOLD", 50)
MAX_ARTICLES_PER_SOURCE: int = _get_int("MAX_ARTICLES_PER_SOURCE", 30)
SCHEDULER_TIME: str = _get_env("SCHEDULER_TIME", "08:00")
APP_HOST: str = _get_env("APP_HOST", "0.0.0.0")
APP_PORT: int = _get_int("APP_PORT", 5000)
APP_DEBUG: bool = _get_env("APP_DEBUG", "false").lower() in {"1", "true", "yes", "on"}

# ── Paths ─────────────────────────────────────────────────────────────────────
LOG_FILE: Path = BASE_DIR / "tracker.log"

# ── Scraper URLs ──────────────────────────────────────────────────────────────
INC42_URL: str = "https://inc42.com/buzz/"
YOURSTORY_RSS_URL: str = "https://yourstory.com/feed"
YOURSTORY_HOME_URL: str = "https://yourstory.com"
ENTRACKR_ROOT_URL: str = "https://entrackr.com"
ENTRACKR_NEWS_URL: str = "https://entrackr.com/news/"
GOOGLE_NEWS_RSS_URL: str = (
    "https://news.google.com/rss/search?q=startup+funding+india+crore&hl=en-IN&gl=IN"
)
CRUNCHBASE_NEWS_URL: str = "https://news.crunchbase.com/?region=india"

FUNDING_KEYWORDS: tuple = (
    "raise", "raised", "fund", "funding",
    "cr", "crore", "million", "series", "seed",
)


def usd_to_inr(amount_usd: float) -> float:
    return amount_usd * USD_TO_INR_RATE


def get_logging_handlers() -> list:
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(formatter)
    return [console_handler, file_handler]


def setup_logging(level: int = logging.INFO) -> None:
    root_logger = logging.getLogger()
    if getattr(root_logger, "_fundedfirst_configured", False):
        return
    root_logger.setLevel(level)
    for handler in get_logging_handlers():
        root_logger.addHandler(handler)
    setattr(root_logger, "_fundedfirst_configured", True)


__all__ = [
    # Gemini
    "GEMINI_API_KEY", "GEMINI_MODEL", "GEMINI_TEMPERATURE", "GEMINI_TOP_P", "GEMINI_ENABLED",
    # Firebase Admin
    "FIREBASE_CREDENTIALS_PATH",
    # Firebase Web
    "FIREBASE_WEB_API_KEY", "FIREBASE_AUTH_DOMAIN", "FIREBASE_PROJECT_ID",
    "FIREBASE_STORAGE_BUCKET", "FIREBASE_MESSAGING_SENDER_ID", "FIREBASE_APP_ID",
    # Email
    "FLASK_SECRET_KEY",
    "EMAIL_USER", "EMAIL_PASSWORD", "RECIPIENT_EMAIL", "EMAIL_SMTP", "EMAIL_PORT",
    # Telegram
    "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
    # CV
    "CV_PDF_PATH",
    # Thresholds
    "USD_TO_INR_RATE", "MIN_FUNDING_INR", "REQUEST_DELAY", "REQUEST_TIMEOUT",
    "HIGH_SCORE_THRESHOLD", "ALERT_SCORE_THRESHOLD", "MAX_ARTICLES_PER_SOURCE",
    "SCHEDULER_TIME", "APP_HOST", "APP_PORT", "APP_DEBUG",
    # Paths
    "LOG_FILE",
    # Scrapers
    "INC42_URL", "YOURSTORY_RSS_URL", "YOURSTORY_HOME_URL",
    "ENTRACKR_ROOT_URL", "ENTRACKR_NEWS_URL",
    "GOOGLE_NEWS_RSS_URL", "CRUNCHBASE_NEWS_URL",
    "FUNDING_KEYWORDS",
    # Helpers
    "usd_to_inr", "setup_logging",
]
