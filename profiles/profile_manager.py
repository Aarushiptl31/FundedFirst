from __future__ import annotations

from typing import Dict


PROFILES: Dict[str, Dict[str, object]] = {
    "backend": {
        "key": "backend",
        "title": "Backend Engineer (Python/Django)",
        "skills": ["Python", "Django", "REST", "SQL", "PostgreSQL"],
        "sectors": ["FinTech", "SaaS", "B2B", "Logistics", "PropTech"],
    },
    "ml": {
        "key": "ml",
        "title": "Machine Learning / Data Engineer",
        "skills": ["Python", "TensorFlow", "PyTorch", "Pandas", "ML"],
        "sectors": ["AI", "HealthTech", "FinTech"],
    },
    "fresher": {
        "key": "fresher",
        "title": "Full-stack / Generalist Fresher",
        "skills": ["Python", "JavaScript", "SQL", "Git", "Problem Solving"],
        "sectors": [
            "D2C",
            "AgriTech",
            "CleanTech",
            "EdTech",
            "SaaS",
            "Logistics",
            "",
        ],
    },
}


def get_profile(key: str) -> Dict[str, object]:
    """Return profile dict by key with fresher as default."""
    return PROFILES.get(key, PROFILES["fresher"])


__all__ = ["PROFILES", "get_profile"]

