from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from config import MIN_FUNDING_INR, USD_TO_INR_RATE, usd_to_inr, setup_logging


setup_logging()
logger = logging.getLogger(__name__)


@dataclass
class FundedStartup:
    """Structured representation of a funded startup article."""

    name: str
    amount_inr: float
    round_type: str
    sector: str
    source: str
    url: str
    date: str
    raw_text: str


_CRORE = 10_000_000.0
_LAKH = 100_000.0
_THOUSAND = 1_000.0
_MILLION = 1_000_000.0
_BILLION = 1_000_000_000.0


def _parse_number(value: str) -> Optional[float]:
    """Parse a numeric string with possible commas into float."""
    try:
        return float(value.replace(",", "").strip())
    except Exception:
        return None


def parse_amount_to_inr(text: str) -> Optional[float]:
    """Parse funding amount text in INR from mixed currency formats."""
    try:
        if not text:
            return None
        t = text.replace("\u20b9", "₹")
        patterns = [
            r"(₹|rs\.?|inr)\s*([\d,\.]+)\s*(crore|cr)\b",
            r"(₹|rs\.?|inr)\s*([\d,\.]+)\s*(lakh|lac)\b",
            r"(₹|rs\.?|inr)\s*([\d,\.]+)\b",
            r"\$?\s*([\d,\.]+)\s*(million|mn|m)\b",
            r"\$?\s*([\d,\.]+)\s*(billion|bn|b)\b",
            r"\$?\s*([\d,\.]+)\s*(thousand|k)\b",
            r"\$\s*([\d,\.]+)\b",
        ]
        t_lower = t.lower()
        for pattern in patterns:
            m = re.search(pattern, t_lower, re.IGNORECASE)
            if not m:
                continue
            groups = m.groups()
            if len(groups) == 3:
                _, num_str, unit = groups
            elif len(groups) == 2:
                num_str, unit = groups
            else:
                num_str, unit = groups[0], ""
            num = _parse_number(num_str)
            if num is None:
                continue
            unit = (unit or "").lower()
            if unit in {"crore", "cr"}:
                return num * _CRORE
            if unit in {"lakh", "lac"}:
                return num * _LAKH
            if unit in {"thousand", "k"}:
                return num * _THOUSAND
            if unit in {"million", "mn", "m"}:
                usd = num * _MILLION
                return usd_to_inr(usd) if USD_TO_INR_RATE else usd
            if unit in {"billion", "bn", "b"}:
                usd = num * _BILLION
                return usd_to_inr(usd) if USD_TO_INR_RATE else usd
            symbol = groups[0] if groups else ""
            if symbol and "$" in symbol:
                return usd_to_inr(num)
            return num
        return None
    except Exception as exc:
        logger.exception("parse_amount_to_inr: error parsing amount: %s", exc)
        return None


def parse_round_type(text: str) -> str:
    """Parse the funding round type from text."""
    try:
        if not text:
            return "Funding"
        t = text.lower()
        mapping = [
            ("pre-seed", "Pre-seed"),
            ("seed", "Seed"),
            ("pre-series a", "Pre-Series A"),
            ("series a", "Series A"),
            ("series b", "Series B"),
            ("series c", "Series C"),
            ("series d", "Series D"),
            ("bridge", "Bridge"),
            ("angel", "Angel"),
            ("strategic", "Strategic"),
            ("growth", "Growth"),
        ]
        for needle, label in mapping:
            if needle in t:
                return label
        if "series" in t:
            return "Funding"
        return "Funding"
    except Exception as exc:
        logger.exception("parse_round_type: error parsing round type: %s", exc)
        return "Funding"


def parse_company_name(title: str) -> str:
    """Infer company name from a funding headline."""
    try:
        if not title:
            return ""

        # Reject generic report/roundup headlines
        SKIP_KEYWORDS = [
            "funding and acquisitions",
            "weekly funding",
            "monthly funding",
            "startup funding",
            "this week",
            "this month",
            "roundup",
            "round up",
        ]
        title_lower = title.lower()
        for kw in SKIP_KEYWORDS:
            if kw in title_lower:
                return ""

        patterns = [
            r"^(.*?)\s+raises\s+",
            r"^(.*?)\s+raised\s+",
            r"^(.*?)\s+bags\s+",
            r"^(.*?)\s+secures\s+",
            r"^(.*?)\s+snags\s+",
            r"^(.*?)\s+gets\s+",
            r"^(.*?)\s+closes\s+",
            r"^(.*?)\s+lands\s+",
        ]
        for pattern in patterns:
            m = re.search(pattern, title, re.IGNORECASE)
            if m:
                name = m.group(1).strip(" :-")
                # Reject if extracted name is too short or is a generic word
                if len(name) >= 2 and name.lower() not in {
                    "funding", "startup", "indian", "india", "", "a", "an", "the"
                }:
                    return name
        words = re.findall(r"[A-Z][\w&]*(?:\s+[A-Z][\w&]*)*", title)
        if words:
            candidate = words[0].strip()
            if len(candidate) >= 2 and candidate.lower() not in {
                "funding", "startup", "indian", "india"
            }:
                return candidate
        return title.split("-")[0].strip()
    except Exception as exc:
        logger.exception("parse_company_name: error parsing company name: %s", exc)
        return title.strip()


def parse_sector(text: str) -> str:
    """Parse startup sector from article text."""
    try:
        if not text:
            return ""
        t = text.lower()
        mapping = {
            "fintech": "FinTech",
            "edtech": "EdTech",
            "healthtech": "HealthTech",
            "health tech": "HealthTech",
            "ai": "AI",
            "artificial intelligence": "AI",
            "saas": "SaaS",
            "logistics": "Logistics",
            "delivery": "Logistics",
            "d2c": "D2C",
            "direct-to-consumer": "D2C",
            "agritech": "AgriTech",
            "agri-tech": "AgriTech",
            "proptech": "PropTech",
            "real estate": "PropTech",
            "cleantech": "CleanTech",
            "clean energy": "CleanTech",
        }
        for needle, label in mapping.items():
            if needle in t:
                return label
        return ""
    except Exception as exc:
        logger.exception("parse_sector: error parsing sector: %s", exc)
        return ""


def meets_threshold(amount_inr: Optional[float]) -> bool:
    """Return True if amount meets configured INR threshold."""
    try:
        if amount_inr is None:
            return False
        return amount_inr >= MIN_FUNDING_INR
    except Exception as exc:
        logger.exception("meets_threshold: error evaluating threshold: %s", exc)
        return False


def current_date_str() -> str:
    """Return today's date as ISO string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


__all__ = [
    "FundedStartup",
    "parse_amount_to_inr",
    "parse_round_type",
    "parse_company_name",
    "parse_sector",
    "meets_threshold",
    "current_date_str",
]

