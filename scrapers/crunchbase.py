from __future__ import annotations

import logging
from typing import List, Tuple

from bs4 import BeautifulSoup

from config import CRUNCHBASE_NEWS_URL, setup_logging
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


class CrunchbaseScraper(BaseScraper):
    """Scraper for Crunchbase News India region funding stories."""

    source_name = "Crunchbase"

    def get_article_urls(self) -> List[Tuple[str, str]]:
        """Return Crunchbase funding article URLs for India region."""
        urls: List[Tuple[str, str]] = []
        html = self._fetch(CRUNCHBASE_NEWS_URL)
        if not html:
            return urls
        try:
            soup = self._soup(html)
            for a in soup.select("a"):
                title = (a.get_text() or "").strip()
                href = a.get("href") or ""
                if not title or not href:
                    continue
                lower = title.lower()
                if "india" not in lower:
                    continue
                if not has_funding_keyword(title):
                    continue
                if href.startswith("/"):
                    href = "https://news.crunchbase.com" + href
                urls.append((title, href))
        except Exception as exc:
            logger.exception("CrunchbaseScraper.get_article_urls: parse error: %s", exc)
        return urls

    def parse_article(self, url: str, html: str) -> FundedStartup | None:
        """Parse Crunchbase article into FundedStartup or fallback gracefully if blocked."""
        try:
            soup = self._soup(html)
            title_tag = soup.find("h1")
            title = (title_tag.get_text() or "").strip() if title_tag else ""
            body_el = soup.find("article") or soup.find("div", {"class": "article__body"})
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
            logger.exception("CrunchbaseScraper.parse_article: error parsing %s: %s", url, exc)
            return None


__all__ = ["CrunchbaseScraper"]

