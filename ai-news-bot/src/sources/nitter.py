from __future__ import annotations

import logging

import httpx

from .rss import RSSFetcher
from .base import RawArticle

logger = logging.getLogger(__name__)

NITTER_MIRRORS = [
    "nitter.net",
    "nitter.privacydev.net",
    "nitter.poast.org",
    "nitter.1d4.us",
    "nitter.kavin.rocks",
]


class NitterFetcher(RSSFetcher):
    _working_mirrors: dict[str, str] = {}

    async def fetch(self, source: dict) -> list[RawArticle]:
        original_url = source["url"]
        source_name = source["name"]

        # Try cached working mirror first
        cached = self._working_mirrors.get(source_name)
        if cached:
            url = self._replace_mirror(original_url, cached)
            source_copy = {**source, "url": url}
            try:
                articles = await super().fetch(source_copy)
                if articles:
                    for article in articles:
                        article.url = self._to_official_url(article.url)
                    return articles
            except Exception:
                logger.debug("Cached mirror %s failed for %s", cached, source_name)
                del self._working_mirrors[source_name]

        # Try all mirrors
        for mirror in NITTER_MIRRORS:
            if mirror == cached:
                continue
            url = self._replace_mirror(original_url, mirror)
            source_copy = {**source, "url": url}

            try:
                articles = await super().fetch(source_copy)
                if articles:
                    logger.info("Nitter mirror %s works for %s", mirror, source_name)
                    self._working_mirrors[source_name] = mirror
                    for article in articles:
                        article.url = self._to_official_url(article.url)
                    return articles
            except Exception as e:
                logger.debug("Nitter mirror %s failed for %s: %s", mirror, source_name, e)
                continue

        logger.warning("All Nitter mirrors failed for %s", source_name)
        return []

    def _replace_mirror(self, url: str, mirror: str) -> str:
        from urllib.parse import urlparse, urlunparse
        parsed = urlparse(url)
        return urlunparse(parsed._replace(netloc=mirror))

    @staticmethod
    def _to_official_url(url: str) -> str:
        """Convert nitter mirror URLs to official x.com URLs."""
        from urllib.parse import urlparse, urlunparse
        parsed = urlparse(url)
        hostname = parsed.hostname or ""
        for mirror in NITTER_MIRRORS:
            if mirror in hostname:
                clean = urlunparse(parsed._replace(
                    scheme="https",
                    netloc="x.com",
                    fragment="",
                ))
                return clean
        return url
