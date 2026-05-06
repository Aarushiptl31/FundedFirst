from __future__ import annotations

import json
import logging
from typing import Any, Dict

try:
    from google import genai
except Exception:  # pragma: no cover - fallback keeps imports working without package
    genai = None  # type: ignore[assignment]

from config import GEMINI_API_KEY, GEMINI_MODEL, setup_logging
from extractor import FundedStartup


setup_logging()
logger = logging.getLogger(__name__)

MAX_RAW_CHARS = 1800
_missing_key_logged = False


def _default_result() -> Dict[str, Any]:
    return {
        "what_they_do": "Indian startup that has recently raised funding.",
        "why_apply_now": "Fresh capital usually triggers hiring across tech and product roles.",
    }


def _build_prompt(startup: FundedStartup) -> str:
    """Build research prompt for summarizing startup."""
    raw_text = (startup.raw_text or "")[:MAX_RAW_CHARS]
    payload = {
        "startup": {
            "name": startup.name,
            "sector": startup.sector,
            "raw_text": raw_text,
            "url": startup.url,
        }
    }
    instructions = (
        "Use ONLY the facts in the provided article text. "
        "If you cannot find a detail, return 'Unknown'. "
        "Keep each answer <= 140 characters, no newlines. "
        'Return JSON exactly: {"what_they_do": "...", "why_apply_now": "..."} '
        "Respond ONLY in valid JSON"
    )
    return json.dumps(payload, ensure_ascii=False) + "\n\n" + instructions


def research_startup(startup: FundedStartup) -> Dict[str, Any]:
    """Call Gemini to research and summarize a startup."""
    default = _default_result()
    global _missing_key_logged
    if not GEMINI_API_KEY or genai is None:
        if not _missing_key_logged:
            logger.warning("research_startup: Gemini API key or google-genai package missing.")
            _missing_key_logged = True
        return default

    try:
        prompt = _build_prompt(startup)
        client = genai.Client(api_key=GEMINI_API_KEY)
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config={"max_output_tokens": 500},
        )
        data = json.loads(response.text)
        what = str(data.get("what_they_do", default["what_they_do"])).strip()
        why = str(data.get("why_apply_now", default["why_apply_now"])).strip()
        return {
            "what_they_do": (what or default["what_they_do"])[:180],
            "why_apply_now": (why or default["why_apply_now"])[:180],
        }
    except Exception as exc:
        logger.exception("research_startup: Gemini error for %s: %s", startup.url, exc)
        return default


__all__ = ["research_startup"]
