from __future__ import annotations

import logging
from typing import List, Tuple

from bs4 import BeautifulSoup

from config import ENTRACKR_NEWS_URL, ENTRACKR_ROOT_URL, setup_logging
from extractor import (
    FundedStartup,
    current_date_str,
    parse_amount_to_inr,
    parse_company_name,
    parse_round_type,
    parse_sector,
)
from scrapers.base import BaseScraper, has_funding_keyword


setup_logging()
logger = logging.getLogger(__name__)


class EntrackrScraper(BaseScraper):
    """Scraper for Entrackr funding news with plugin-style URLs."""

    source_name = "Entrackr"

    def _collect_from(self, url: str) -> List[Tuple[str, str]]:
        """Collect article URLs from a specific Entrackr URL."""
        urls: List[Tuple[str, str]] = []
        html = self._fetch(url)
        if not html:
            return urls
        try:
            soup = self._soup(html)
            for a in soup.select("a"):
                title = (a.get_text() or "").strip()
                href = a.get("href") or ""
                if not title or not href:
                    continue
                if not has_funding_keyword(title):
                    continue
                if href.startswith("/"):
                    href = "https://entrackr.com" + href
                urls.append((title, href))
        except Exception as exc:
            logger.exception("EntrackrScraper._collect_from: parse error for %s: %s", url, exc)
        return urls

    def get_article_urls(self) -> List[Tuple[str, str]]:
        """Return Entrackr funding article URLs from multiple entry points."""
        all_urls: List[Tuple[str, str]] = []
        for url in (ENTRACKR_ROOT_URL, ENTRACKR_NEWS_URL):
            try:
                all_urls.extend(self._collect_from(url))
            except Exception as exc:
                logger.exception("EntrackrScraper.get_article_urls: error for %s: %s", url, exc)
        # De-duplicate by URL while preserving order
        seen = set()
        unique: List[Tuple[str, str]] = []
        for title, href in all_urls:
            if href in seen:
                continue
            seen.add(href)
            unique.append((title, href))
        return unique

    def parse_article(self, url: str, html: str) -> FundedStartup | None:
        """Parse Entrackr article into FundedStartup."""
        try:
            soup = self._soup(html)
            title_tag = soup.find("h1")
            title = (title_tag.get_text() or "").strip() if title_tag else ""
            body_el = soup.find("article") or soup.find("div", {"class": "post-content"})
            body = (body_el.get_text(separator=" ") or "").strip() if body_el else ""
            combined = f"{title}\n{body}"
            amount = parse_amount_to_inr(combined)
            if amount is None:
                return None
            round_type = parse_round_type(combined)
            sector = parse_sector(combined)
            company_name = parse_company_name(title or url)
            return FundedStartup(
                name=company_name,
                amount_inr=amount,
                round_type=round_type,
                sector=sector,
                source=self.source_name,
                url=url,
                date=current_date_str(),
                raw_text=combined,
            )
        except Exception as exc:
            logger.exception("EntrackrScraper.parse_article: error parsing %s: %s", url, exc)
            return None


__all__ = ["EntrackrScraper"]

