from __future__ import annotations


def get_confidence_badge(level: str) -> str:
    """Return a readable badge string for a confidence level."""
    normalized = (level or "").upper()
    if normalized == "HIGH":
        return "HIGH CONFIDENCE - Apply immediately"
    if normalized == "LOW":
        return "LOW CONFIDENCE - Research before applying"
    return "VERIFY FIRST - Check manually"


__all__ = ["get_confidence_badge"]
