from __future__ import annotations

from typing import Dict

from .profile_manager import PROFILES, get_profile


SECTOR_PROFILE_MAP: Dict[str, str] = {
    "FinTech": "backend",
    "SaaS": "backend",
    "B2B": "backend",
    "Logistics": "backend",
    "PropTech": "backend",
    "AI": "ml",
    "HealthTech": "ml",
    "EdTech": "fresher",
    "D2C": "fresher",
    "AgriTech": "fresher",
    "CleanTech": "fresher",
    "": "fresher",
}


def get_best_profile(sector: str) -> Dict[str, object]:
    """Return the best profile dict for a given sector."""
    key = SECTOR_PROFILE_MAP.get(sector or "", "fresher")
    return get_profile(key)


__all__ = ["SECTOR_PROFILE_MAP", "get_best_profile"]

