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
        "credibility": "HIGH",
        "is_confirmed": True,
        "red_flags": [],
        "recommendation": "APPLY",
    }


def _build_prompt(startup: FundedStartup) -> str:
    """Build fake news evaluation prompt for funding article."""
    raw_text = (startup.raw_text or "")[:MAX_RAW_CHARS]
    payload = {
        "startup": {
            "name": startup.name,
            "amount_inr": startup.amount_inr,
            "round_type": startup.round_type,
            "sector": startup.sector,
            "raw_text": raw_text,
            "url": startup.url,
        },
        "red_flags_to_detect": [
            "\"reportedly\", \"sources say\", \"plans to raise\", \"in talks\" -> UNCONFIRMED",
            "No investor name -> SUSPICIOUS",
            "Seed round above INR 100 Cr -> SUSPICIOUS",
            "Press release language -> PAID PR",
            "Amount exactly round number -> PR LIKELY",
        ],
    }
    instructions = (
        "You are checking if a startup funding news article is credible. "
        "Use ONLY the supplied text and URL metadata; do not guess investor names or amounts. "
        "Return JSON exactly: "
        '{"credibility": "HIGH|MEDIUM|LOW", '
        '"is_confirmed": true, '
        '"red_flags": ["..."], '
        '"recommendation": "APPLY|VERIFY_FIRST|SKIP"}. '
        "Respond ONLY in valid JSON"
    )
    return json.dumps(payload, ensure_ascii=False) + "\n\n" + instructions


def evaluate_fake_news(startup: FundedStartup) -> Dict[str, Any]:
    """Evaluate credibility of a startup funding article using Gemini."""
    default = _default_result()
    global _missing_key_logged
    if not GEMINI_API_KEY or genai is None:
        if not _missing_key_logged:
            logger.warning("evaluate_fake_news: Gemini API key or google-genai package missing.")
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
        credibility = str(data.get("credibility", default["credibility"])).upper()
        if credibility not in {"HIGH", "MEDIUM", "LOW"}:
            credibility = "MEDIUM"
        is_confirmed = bool(data.get("is_confirmed", default["is_confirmed"]))
        red_flags = data.get("red_flags", default["red_flags"])
        if not isinstance(red_flags, list):
            red_flags = default["red_flags"]
        recommendation = str(data.get("recommendation", default["recommendation"])).upper()
        if recommendation not in {"APPLY", "VERIFY_FIRST", "SKIP"}:
            recommendation = "VERIFY_FIRST"
        return {
            "credibility": credibility,
            "is_confirmed": is_confirmed,
            "red_flags": red_flags,
            "recommendation": recommendation,
        }
    except Exception as exc:
        logger.exception("evaluate_fake_news: Gemini error for %s: %s", startup.url, exc)
        return default


__all__ = ["evaluate_fake_news"]
