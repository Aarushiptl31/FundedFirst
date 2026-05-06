from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

try:
    from google import genai
except Exception:  # pragma: no cover - fallback keeps imports working without package
    genai = None  # type: ignore[assignment]

from config import GEMINI_API_KEY, GEMINI_MODEL, setup_logging
from database import get_pending_followups as db_get_pending_followups


setup_logging()
logger = logging.getLogger(__name__)


def get_pending_followups(conn: Any = None) -> List[Dict[str, Any]]:
    """Return applications that need follow-ups using database helper."""
    return db_get_pending_followups()


def _build_followup_prompt(startup_name: str, days_since: int) -> str:
    """Build prompt text for follow-up email drafting."""
    tone = "gentle check-in" if days_since <= 6 else "final nudge with a fresh angle"
    payload = {
        "startup_name": startup_name,
        "days_since_first_email": days_since,
        "tone": tone,
    }
    instructions = (
        "Write a very short follow-up email to a startup you previously cold emailed for a job opportunity. "
        "Keep it 80-120 words, and do not sound pushy. "
        "If this is around day 4, be a gentle check-in. "
        "If this is around day 10, be a final nudge with a new angle or update. "
        'Return JSON exactly: {"body": "...", "tone": "gentle|final"}. '
        "Respond ONLY in valid JSON"
    )
    return json.dumps(payload, ensure_ascii=False) + "\n\n" + instructions


def draft_followup(startup_name: str, days_since: int) -> str:
    """Use Gemini to draft a follow-up email body."""
    default = (
        f"Hi,\n\nJust checking in regarding my earlier email about opportunities at {startup_name}. "
        "I remain very interested and would love to contribute.\n\nThanks,\nStudent"
    )
    if not GEMINI_API_KEY or genai is None:
        return default
    try:
        prompt = _build_followup_prompt(startup_name, days_since)
        client = genai.Client(api_key=GEMINI_API_KEY)
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config={"max_output_tokens": 500},
        )
        data = json.loads(response.text)
        return str(data.get("body", default)).strip() or default
    except Exception as exc:
        logger.exception("draft_followup: Gemini error for %s: %s", startup_name, exc)
        return default


__all__ = ["get_pending_followups", "draft_followup"]
