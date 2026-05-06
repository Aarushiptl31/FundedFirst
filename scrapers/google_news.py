from __future__ import annotations

import logging
from typing import List, Tuple
from xml.etree import ElementTree as ET

from bs4 import BeautifulSoup

from config import GOOGLE_NEWS_RSS_URL, setup_logging
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


class GoogleNewsScraper(BaseScraper):
    """Scraper for Google News RSS funding search."""

    source_name = "GoogleNews"

    def get_article_urls(self) -> List[Tuple[str, str]]:
        """Return funding article URLs from Google News RSS."""
        urls: List[Tuple[str, str]] = []
        xml = self._fetch(GOOGLE_NEWS_RSS_URL)
        if not xml:
            return urls
        try:
            root = ET.fromstring(xml)
            for item in root.findall(".//item"):
                title_el = item.find("title")
                link_el  = item.find("link")
                title = (title_el.text or "").strip() if title_el is not None else ""
                link  = (link_el.text or "").strip()  if link_el  is not None else ""
                if not title or not link:
                    continue
                if not has_funding_keyword(title):
                    continue
                urls.append((title, link))
        except Exception as exc:
            logger.exception("GoogleNewsScraper.get_article_urls: XML parse error: %s", exc)
        return urls

    def parse_article(self, url: str, html: str) -> FundedStartup | None:
        """Parse funding info from article page."""
        try:
            soup = BeautifulSoup(html, "html.parser")
            text = soup.get_text(separator=" ", strip=True)[:3000]
            amount = parse_amount_to_inr(text)
            if not amount:
                return None
            return FundedStartup(
                name=parse_company_name(text),
                amount_inr=amount,
                round_type=parse_round_type(text),
                sector=parse_sector(text),
                source=self.source_name,
                url=url,
                date=current_date_str(),
                raw_text=text[:500],
            )
        except Exception as exc:
            logger.exception("GoogleNewsScraper.parse_article: error for %s: %s", url, exc)
            return None


__all__ = ["GoogleNewsScraper"]
