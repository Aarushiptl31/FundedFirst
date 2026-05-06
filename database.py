from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from config import BASE_DIR, FIREBASE_CREDENTIALS_PATH, setup_logging

setup_logging()
logger = logging.getLogger(__name__)

# ── Firebase Admin SDK ────────────────────────────────────────────────────────
_firebase_app = None
_firestore_client = None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_iso() -> str:
    return _utc_now().isoformat()


def _credential_path() -> Path:
    """Resolve Firebase credentials relative to the project root when needed."""
    path = Path(FIREBASE_CREDENTIALS_PATH).expanduser()
    if not path.is_absolute():
        path = BASE_DIR / path
    return path


def _init_firebase() -> None:
    """Initialise Firebase Admin SDK once."""
    global _firebase_app
    if _firebase_app is not None:
        return
    try:
        import firebase_admin
        from firebase_admin import credentials

        cred_path = _credential_path()
        if not cred_path.exists():
            logger.warning(
                "database: Firebase credentials not found at '%s'. "
                "Firestore will be unavailable until the file exists.",
                cred_path,
            )
            return
        cred = credentials.Certificate(str(cred_path))
        _firebase_app = firebase_admin.initialize_app(cred)
        logger.info("database: Firebase Admin SDK initialised")
    except Exception as exc:
        logger.exception("database: Firebase init failed: %s", exc)


def _get_firestore_client():
    """Return a Firestore client, initialising Firebase if needed."""
    global _firestore_client
    if _firestore_client is not None:
        return _firestore_client
    _init_firebase()
    try:
        from firebase_admin import firestore
        _firestore_client = firestore.client()
        return _firestore_client
    except Exception as exc:
        logger.exception("database: could not get Firestore client: %s", exc)
        return None


def _url_to_doc_id(url: str) -> str:
    """Convert a URL to a safe Firestore document ID (SHA-256, 16 chars)."""
    return hashlib.sha256(url.encode()).hexdigest()[:16]


# ── Public API ────────────────────────────────────────────────────────────────

def init_db() -> None:
    """Initialise Firestore connection (no-op if credentials not present)."""
    _get_firestore_client()


def verify_firebase_token(id_token: str) -> dict:
    """Verify a Firebase ID token and return user info dict."""
    if not id_token or not id_token.strip():
        logger.warning("verify_firebase_token: empty token received")
        return {}
    try:
        _init_firebase()
        if _firebase_app is None:
            logger.error(
                "verify_firebase_token: Firebase Admin SDK not initialised. "
                "Check FIREBASE_CREDENTIALS_PATH in .env and that firebase_credentials.json exists."
            )
            return {}
        from firebase_admin import auth

        # check_revoked=False avoids an extra Firestore network call per request.
        # Some local Windows/browser clock combinations make fresh Firebase tokens
        # verify as a few seconds "too early", so retry that exact case briefly.
        decoded = None
        for attempt in range(4):
            try:
                decoded = auth.verify_id_token(
                    id_token,
                    check_revoked=False,
                    clock_skew_seconds=60,
                )
                break
            except Exception as exc:
                if "Token used too early" not in str(exc) or attempt == 3:
                    raise
                logger.warning(
                    "verify_firebase_token: token used too early; retrying (%d/3)",
                    attempt + 1,
                )
                time.sleep(2)
        if not decoded:
            return {}
        uid = decoded.get("uid")
        if not uid:
            logger.error("verify_firebase_token: decoded token has no uid")
            return {}
        return {
            "uid": uid,
            "email": decoded.get("email", ""),
            "name": decoded.get("name", ""),
            "picture": decoded.get("picture", ""),
        }
    except Exception as exc:
        # Log the specific error type to help diagnose issues
        exc_type = type(exc).__name__
        logger.error("verify_firebase_token: %s — %s", exc_type, exc)
        return {}


def get_user_profile(uid: str) -> dict:
    """Get user profile from Firestore."""
    try:
        db = _get_firestore_client()
        if db is None:
            return {}
        doc = db.collection("users").document(uid).get()
        if doc.exists:
            return doc.to_dict()
        return {}
    except Exception as exc:
        logger.exception("get_user_profile: %s", exc)
        return {}


def save_user_profile(uid: str, profile: dict) -> bool:
    """Save / update user profile in Firestore."""
    try:
        db = _get_firestore_client()
        if db is None:
            return False
        db.collection("users").document(uid).set(profile, merge=True)
        return True
    except Exception as exc:
        logger.exception("save_user_profile: %s", exc)
        return False


def get_user_startups(uid: str, limit: int = 100) -> list:
    """Get startups for a specific user ordered by score descending."""
    try:
        from firebase_admin import firestore
        db = _get_firestore_client()
        if db is None:
            return []
        docs = (
            db.collection("users")
            .document(uid)
            .collection("startups")
            .order_by("score", direction=firestore.Query.DESCENDING)
            .limit(limit)
            .stream()
        )
        return [doc.to_dict() for doc in docs]
    except Exception as exc:
        logger.exception("get_user_startups: %s", exc)
        return []


def insert_user_startup(uid: str, record: dict) -> bool:
    """Insert a startup into a user's personal Firestore collection."""
    try:
        db = _get_firestore_client()
        if db is None:
            return False
        url = str(record.get("url", ""))
        doc_id = _url_to_doc_id(url)
        record["created_at"] = _utc_iso()
        (
            db.collection("users")
            .document(uid)
            .collection("startups")
            .document(doc_id)
            .set(record, merge=False)
        )
        return True
    except Exception as exc:
        logger.exception("insert_user_startup: %s", exc)
        return False


def insert_user_startups(uid: str, records: list) -> int:
    """Insert multiple startups for a user, skipping duplicates."""
    inserted = 0
    try:
        db = _get_firestore_client()
        if db is None:
            return 0
        user_ref = db.collection("users").document(uid).collection("startups")
        for record in records:
            url = str(record.get("url", ""))
            doc_id = _url_to_doc_id(url)
            existing = user_ref.document(doc_id).get()
            if existing.exists:
                continue
            r = dict(record)
            r["created_at"] = _utc_iso()
            user_ref.document(doc_id).set(r, merge=False)
            inserted += 1
    except Exception as exc:
        logger.exception("insert_user_startups: %s", exc)
    return inserted


def get_user_applications(uid: str, limit: int = 50) -> list:
    """Get applications for a specific user ordered by date descending."""
    try:
        from firebase_admin import firestore
        db = _get_firestore_client()
        if db is None:
            return []
        docs = (
            db.collection("users")
            .document(uid)
            .collection("applications")
            .order_by("applied_date", direction=firestore.Query.DESCENDING)
            .limit(limit)
            .stream()
        )
        results = []
        for doc in docs:
            data = doc.to_dict()
            data["id"] = doc.id
            results.append(data)
        return results
    except Exception as exc:
        logger.exception("get_user_applications: %s", exc)
        return []


def insert_user_application(uid: str, application: dict) -> bool:
    """Insert an application record for a specific user."""
    try:
        db = _get_firestore_client()
        if db is None:
            return False
        app = dict(application)
        app["applied_date"] = _utc_iso()
        app["status"] = "APPLIED"
        app["followup_1_done"] = False
        app["followup_2_done"] = False
        db.collection("users").document(uid).collection("applications").add(app)
        return True
    except Exception as exc:
        logger.exception("insert_user_application: %s", exc)
        return False


def get_startups_since(days: int = 7, limit: int = 100) -> list:
    """Return recent startups across all users for legacy digest mode."""
    try:
        db = _get_firestore_client()
        if db is None:
            return []
        cutoff = _utc_now().timestamp() - (max(days, 1) * 86400)
        records = []
        for doc in db.collection_group("startups").limit(limit * 3).stream():
            data = doc.to_dict() or {}
            created_at = str(data.get("created_at") or data.get("date") or "")
            try:
                created_ts = datetime.fromisoformat(created_at.replace("Z", "+00:00")).timestamp()
            except ValueError:
                created_ts = _utc_now().timestamp()
            if created_ts >= cutoff:
                records.append(data)
        records.sort(key=lambda item: int(item.get("score") or 0), reverse=True)
        return records[:limit]
    except Exception as exc:
        logger.exception("get_startups_since: %s", exc)
        return []


# ── Legacy stubs (kept so scrapers / email_sender don't break) ────────────────

def get_pending_followups() -> List[Dict[str, Any]]:
    """Legacy stub — follow-ups are now per-user in Firestore."""
    return []


def update_followup_status(
    application_id: int, followup_number: int, when: Optional[datetime] = None
) -> None:
    """Legacy stub — not used in multi-user Firestore model."""
    pass


__all__ = [
    "init_db",
    "verify_firebase_token",
    "get_user_profile",
    "save_user_profile",
    "get_user_startups",
    "insert_user_startup",
    "insert_user_startups",
    "get_user_applications",
    "insert_user_application",
    "get_startups_since",
    "get_pending_followups",
    "update_followup_status",
]
