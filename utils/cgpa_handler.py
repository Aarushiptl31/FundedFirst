from __future__ import annotations

from typing import Dict


def get_cgpa_strategy(cgpa: float) -> Dict[str, str]:
    """Return CGPA strategy bucket and guidance for a given CGPA."""
    if cgpa >= 8.0:
        return {
            "level": "high",
            "rule": "mention_confidently",
            "guidance": "Highlight CGPA clearly as a strength.",
        }
    if cgpa >= 7.0:
        return {
            "level": "medium",
            "rule": "mention_briefly",
            "guidance": "Mention CGPA briefly but focus more on skills and projects.",
        }
    if cgpa >= 6.0:
        return {
            "level": "low",
            "rule": "skip_use_projects",
            "guidance": "Avoid emphasizing CGPA; lean on strong projects and internships.",
        }
    return {
        "level": "very_low",
        "rule": "never_mention",
        "guidance": "Do not mention CGPA; position yourself as a builder with proof of work.",
    }


__all__ = ["get_cgpa_strategy"]

