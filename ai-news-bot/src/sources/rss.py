from __future__ import annotations

import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import feedparser
import httpx
from bs4 import BeautifulSoup

from .base import BaseFetcher, RawArticle

logger = logging.getLogger(__name__)

USER_AGENT = (
    "AINewsBot/0.1 (Telegram AI Digest; +https://github.com/redpeak)"
)


class RSSFetcher(BaseFetcher):
    def __init__(self, client: httpx.AsyncClient | None = None):
        self._client = client

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                headers={"User-Agent": USER_AGENT},
                follow_redirects=True,
            )
        return self._client

    async def fetch(self, source: dict) -> list[RawArticle]:
        client = await self._get_client()
        try:
            resp = await client.get(source["url"])
            resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.warning("Failed to fetch %s: %s", source["name"], e)
            return []

        feed = feedparser.parse(resp.text)
        articles = []

        is_reddit = "reddit.com" in source.get("url", "")

        for entry in feed.entries[:50]:
            title = entry.get("title", "").strip()
            if not title:
                continue

            url = entry.get("link", "")
            if not url:
                continue

            content = self._extract_content(entry)

            # For Reddit: extract original external link from post
            if is_reddit:
                external = self._extract_reddit_external_url(entry)
                if external:
                    url = external

            published = self._parse_date(entry)

            image_url = self._extract_image(entry)

            articles.append(RawArticle(
                url=url,
                title=title,
                content=content,
                published_at=published,
                source_name=source["name"],
                source_id=source["id"],
                image_url=image_url,
            ))

        logger.info("Fetched %d articles from %s", len(articles), source["name"])
        return articles

    @staticmethod
    def _extract_reddit_external_url(entry) -> str | None:
        """Extract the original external URL from a Reddit link post."""
        import re
        content_html = ""
        if "content" in entry and entry.content:
            content_html = entry.content[0].get("value", "")
        elif "summary" in entry:
            content_html = entry.get("summary", "")

        if not content_html:
            return None

        # Reddit link posts have "[link]" pointing to external URL
        match = re.search(
            r'<a\s+href="(https?://[^"]+)"[^>]*>\s*\[link\]\s*</a>',
            content_html,
        )
        if match:
            link = match.group(1)
            # Skip if the link points back to reddit itself
            if "reddit.com" not in link and "redd.it" not in link:
                return link
        return None

    @staticmethod
    def _extract_image(entry) -> str | None:
        """Extract image URL from RSS entry (media:content, enclosure, or inline img)."""
        # media:content / media:thumbnail (feedparser stores as media_content / media_thumbnail)
        for media_list in (entry.get("media_content", []), entry.get("media_thumbnail", [])):
            for media in media_list:
                url = media.get("url", "")
                media_type = media.get("type", "")
                if url and ("image" in media_type or url.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".gif"))):
                    return url

        # enclosure
        for enc in entry.get("enclosures", []):
            url = enc.get("href", "") or enc.get("url", "")
            enc_type = enc.get("type", "")
            if url and "image" in enc_type:
                return url

        # Fallback: first <img> in content/summary HTML
        content_html = ""
        content_list = entry.get("content")
        if content_list:
            content_html = content_list[0].get("value", "") if content_list else ""
        elif "summary" in entry:
            content_html = entry.get("summary", "")

        if content_html and "<img" in content_html:
            import re
            img_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', content_html)
            if img_match:
                img_url = img_match.group(1)
                # Skip tiny icons/badges (common in Reddit)
                if not any(skip in img_url for skip in ("emoji", "award", "icon", "badge", "flair")):
                    return img_url

        return None

    def _extract_content(self, entry) -> str:
        content = ""

        if "content" in entry and entry.content:
            content = entry.content[0].get("value", "")
        elif "summary" in entry:
            content = entry.get("summary", "")
        elif "description" in entry:
            content = entry.get("description", "")

        if "<" in content:
            soup = BeautifulSoup(content, "lxml")
            content = soup.get_text(separator=" ", strip=True)

        return content[:5000]

    def _parse_date(self, entry) -> datetime | None:
        for field in ("published", "updated", "created"):
            val = entry.get(field)
            if val:
                try:
                    return parsedate_to_datetime(val)
                except Exception:
                    pass

            parsed = entry.get(f"{field}_parsed")
            if parsed:
                try:
                    from time import mktime
                    return datetime.fromtimestamp(mktime(parsed), tz=timezone.utc)
                except Exception:
                    pass

        return None

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
