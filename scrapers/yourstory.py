from __future__ import annotations

import logging
from typing import List, Tuple
from xml.etree import ElementTree as ET

from bs4 import BeautifulSoup

from config import YOURSTORY_HOME_URL, YOURSTORY_RSS_URL, setup_logging
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


class YourStoryScraper(BaseScraper):
    """Scraper for YourStory funding news via RSS or homepage."""

    source_name = "YourStory"

    def _rss_article_urls(self) -> List[Tuple[str, str]]:
        """Fetch article URLs from YourStory RSS feed."""
        urls: List[Tuple[str, str]] = []
        xml = self._fetch(YOURSTORY_RSS_URL)
        if not xml:
            return urls
        try:
            root = ET.fromstring(xml)
            for item in root.findall(".//item"):
                title_el = item.find("title")
                link_el = item.find("link")
                title = (title_el.text or "").strip() if title_el is not None else ""
                link = (link_el.text or "").strip() if link_el is not None else ""
                if not title or not link:
                    continue
                if not has_funding_keyword(title):
                    continue
                urls.append((title, link))
        except Exception as exc:
            logger.exception("YourStoryScraper._rss_article_urls: XML parse error: %s", exc)
        return urls

    def _html_article_urls(self) -> List[Tuple[str, str]]:
        """Fallback: fetch article URLs from YourStory homepage."""
        urls: List[Tuple[str, str]] = []
        html = self._fetch(YOURSTORY_HOME_URL)
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
                    href = "https://yourstory.com" + href
                urls.append((title, href))
        except Exception as exc:
            logger.exception("YourStoryScraper._html_article_urls: parse error: %s", exc)
        return urls

    def get_article_urls(self) -> List[Tuple[str, str]]:
        """Return funding article URLs, using RSS or HTML fallback."""
        urls = self._rss_article_urls()
        if urls:
            return urls
        return self._html_article_urls()

    def parse_article(self, url: str, html: str) -> FundedStartup | None:
        """Parse YourStory article into FundedStartup."""
        try:
            soup = self._soup(html)
            title_tag = soup.find("h1")
            title = (title_tag.get_text() or "").strip() if title_tag else ""
            body_el = soup.find("article") or soup.find("div", {"class": "story-detail"})
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
            logger.exception("YourStoryScraper.parse_article: error parsing %s: %s", url, exc)
            return None


__all__ = ["YourStoryScraper"]

