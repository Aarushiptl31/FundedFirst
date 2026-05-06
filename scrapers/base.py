from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from typing import Iterator, List, Tuple

import requests
from bs4 import BeautifulSoup

from config import (
    FUNDING_KEYWORDS,
    MAX_ARTICLES_PER_SOURCE,
    REQUEST_DELAY,
    REQUEST_TIMEOUT,
    setup_logging,
)
from extractor import FundedStartup, current_date_str, meets_threshold


setup_logging()
logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0 Safari/537.36"
    )
}


class BaseScraper(ABC):
    """Abstract base class for all startup funding scrapers."""

    source_name: str = "base"

    def _fetch(self, url: str) -> str | None:
        """Fetch URL content as text with headers and configured request delay."""
        try:
            if REQUEST_DELAY > 0:
                time.sleep(REQUEST_DELAY)
            resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            if resp.status_code != 200:
                logger.warning(
                    "%s._fetch: non-200 status %s for %s",
                    self.__class__.__name__,
                    resp.status_code,
                    url,
                )
                return None
            return resp.text
        except Exception as exc:
            logger.exception("%s._fetch: error fetching %s: %s", self.__class__.__name__, url, exc)
            return None

    def _soup(self, html: str) -> BeautifulSoup:
        """Create BeautifulSoup parser instance."""
        return BeautifulSoup(html, "html.parser")

    @abstractmethod
    def get_article_urls(self) -> List[Tuple[str, str]]:
        """Return list of (title, url) tuples for potential funding articles."""

    @abstractmethod
    def parse_article(self, url: str, html: str) -> FundedStartup | None:
        """Parse article page into FundedStartup if threshold is met."""

    def scrape(self) -> Iterator[FundedStartup]:
        """Iterate over qualifying funded startups from this source."""
        try:
            articles = self.get_article_urls()[:MAX_ARTICLES_PER_SOURCE]
        except Exception as exc:
            logger.exception("%s.scrape: error getting article URLs: %s", self.__class__.__name__, exc)
            return
        for title, url in articles:
            try:
                html = self._fetch(url)
                if not html:
                    continue
                startup = self.parse_article(url, html)
                if not startup:
                    continue
                # Skip if name is empty or generic
                bad_names = {"funding", "startup", "indian", "india", "", "a", "the"}
                if not startup.name or startup.name.lower().strip() in bad_names:
                    logger.debug(
                        "%s.scrape: skipping article with generic name '%s': %s",
                        self.__class__.__name__, startup.name, url,
                    )
                    continue
                if meets_threshold(startup.amount_inr):
                    yield startup
            except Exception as exc:
                logger.exception(
                    "%s.scrape: error processing article %s: %s",
                    self.__class__.__name__,
                    url,
                    exc,
                )


def has_funding_keyword(title: str) -> bool:
    """Return True if title includes any funding keyword and is not a weekly/monthly report."""
    t = title.lower()
    # Skip roundup/report articles — they cause generic "Funding" company names
    SKIP_PATTERNS = [
        "this week",
        "this month",
        "weekly funding",
        "monthly funding",
        "funding roundup",
        "round up",
        "acquisitions in indian startup",
        "funding and acquisitions",
        "startup ecosystem",
    ]
    for skip in SKIP_PATTERNS:
        if skip in t:
            return False
    return any(kw in t for kw in FUNDING_KEYWORDS)


__all__ = ["BaseScraper", "has_funding_keyword"]

