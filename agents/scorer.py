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
        "score": 50,
        "confidence": "MEDIUM",
        "role_match": "Software Engineer",
        "reason": "Fallback score used because Gemini scoring was unavailable.",
    }


def _build_prompt(startup: FundedStartup) -> str:
    payload = {
        "startup": {
            "name": startup.name,
            "amount_inr": startup.amount_inr,
            "round_type": startup.round_type,
            "sector": startup.sector,
            "source": startup.source,
            "url": startup.url,
            "raw_text": (startup.raw_text or "")[:MAX_RAW_CHARS],
        }
    }
    instructions = (
        "Score this funded Indian startup as an opportunity for a fresher job seeker. "
        "Use only the supplied data. Prefer recently funded, credible, hiring-likely companies. "
        'Return JSON exactly: {"score": 0, "confidence": "HIGH|MEDIUM|LOW", '
        '"role_match": "best role title", "reason": "short reason"}. '
        "Respond ONLY in valid JSON"
    )
    return json.dumps(payload, ensure_ascii=False) + "\n\n" + instructions


def score_startup(startup: FundedStartup) -> Dict[str, Any]:
    """Score a startup opportunity using Gemini."""
    default = _default_result()
    global _missing_key_logged
    if not GEMINI_API_KEY or genai is None:
        if not _missing_key_logged:
            logger.warning("score_startup: Gemini API key or google-genai package missing.")
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
        try:
            score = max(0, min(100, int(data.get("score", default["score"]))))
        except (TypeError, ValueError):
            score = default["score"]
        confidence = str(data.get("confidence", default["confidence"])).upper()
        if confidence not in {"HIGH", "MEDIUM", "LOW"}:
            confidence = default["confidence"]
        return {
            "score": score,
            "confidence": confidence,
            "role_match": str(data.get("role_match", default["role_match"])).strip()
            or default["role_match"],
            "reason": str(data.get("reason", default["reason"])).strip() or default["reason"],
        }
    except Exception as exc:
        logger.exception("score_startup: Gemini error for %s: %s", startup.url, exc)
        return default


__all__ = ["score_startup"]
