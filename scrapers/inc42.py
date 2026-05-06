from __future__ import annotations

import logging
from typing import List, Tuple

from bs4 import BeautifulSoup

from config import INC42_URL, setup_logging
from extractor import FundedStartup, current_date_str, parse_amount_to_inr, parse_company_name, parse_round_type, parse_sector
from scrapers.base import BaseScraper, has_funding_keyword


setup_logging()
logger = logging.getLogger(__name__)


class Inc42Scraper(BaseScraper):
    """Scraper for Inc42 buzz funding articles."""

    source_name = "Inc42"

    def get_article_urls(self) -> List[Tuple[str, str]]:
        """Return recent Inc42 buzz article titles and URLs."""
        urls: List[Tuple[str, str]] = []
        html = self._fetch(INC42_URL)
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
                    href = "https://inc42.com" + href
                urls.append((title, href))
        except Exception as exc:
            logger.exception("Inc42Scraper.get_article_urls: parsing error: %s", exc)
        return urls

    def parse_article(self, url: str, html: str) -> FundedStartup | None:
        """Parse Inc42 article into FundedStartup."""
        try:
            soup = self._soup(html)
            title_tag = soup.find("h1")
            title = (title_tag.get_text() or "").strip() if title_tag else ""
            body_el = soup.find("article") or soup.find("div", {"class": "single-post"})
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
            logger.exception("Inc42Scraper.parse_article: error parsing %s: %s", url, exc)
            return None


__all__ = ["Inc42Scraper"]

