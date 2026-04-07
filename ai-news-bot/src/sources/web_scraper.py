from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup

from .base import BaseFetcher, RawArticle

logger = logging.getLogger(__name__)

USER_AGENT = (
    "AINewsBot/0.1 (Telegram AI Digest; +https://github.com/redpeak)"
)

# Scraping configs for known sites
SCRAPER_CONFIGS = {
    "The Batch": {
        "article_selector": "article, .post-card, .batch-article",
        "title_selector": "h2, h3, .post-card__title",
        "link_selector": "a",
        "base_url": "https://www.deeplearning.ai",
    },
    "Anthropic Blog": {
        "article_selector": "a[href*='/research/'], a[href*='/news/'], a[href*='/engineering/']",
        "title_selector": "h3, h2, span, div",
        "link_selector": "",
        "base_url": "https://www.anthropic.com",
        "use_parent_as_link": True,
    },
}


MAX_RESPONSE_SIZE = 5 * 1024 * 1024  # 5 MB


class WebScraperFetcher(BaseFetcher):
    def __init__(self):
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                headers={"User-Agent": USER_AGENT},
                follow_redirects=True,
                max_redirects=5,
            )
        return self._client

    async def fetch(self, source: dict) -> list[RawArticle]:
        client = await self._get_client()
        config = SCRAPER_CONFIGS.get(source["name"], {})

        try:
            resp = await client.get(source["url"])
            resp.raise_for_status()
            if len(resp.content) > MAX_RESPONSE_SIZE:
                logger.warning("Response too large for %s: %d bytes", source["name"], len(resp.content))
                return []
        except httpx.HTTPError as e:
            logger.warning("Failed to scrape %s: %s", source["name"], e)
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        articles = []

        article_selector = config.get("article_selector", "article")
        title_selector = config.get("title_selector", "h2, h3")
        link_selector = config.get("link_selector", "a")
        base_url = config.get("base_url", "")

        use_parent_as_link = config.get("use_parent_as_link", False)

        for el in soup.select(article_selector)[:20]:
            title = ""
            if title_selector:
                title_el = el.select_one(title_selector)
                if title_el:
                    title = title_el.get_text(strip=True)
            if not title:
                title = el.get_text(strip=True)[:120]
            if not title or len(title) < 5:
                continue

            url = ""
            if use_parent_as_link and el.name == "a" and el.get("href"):
                url = el["href"]
            elif link_selector:
                link_el = el.select_one(link_selector)
                if link_el and link_el.get("href"):
                    url = link_el["href"]

            if url and url.startswith("/"):
                url = base_url + url

            content = el.get_text(separator=" ", strip=True)[:3000]

            # Extract image from article element or nearby
            image_url = None
            img_el = el.select_one("img[src]")
            if img_el:
                img_src = img_el.get("src", "")
                if img_src and img_src.startswith("/"):
                    img_src = base_url + img_src
                if img_src and img_src.startswith("http"):
                    image_url = img_src

            articles.append(RawArticle(
                url=url or source["url"],
                title=title,
                content=content,
                published_at=datetime.now(timezone.utc),
                source_name=source["name"],
                source_id=source["id"],
                image_url=image_url,
            ))

        logger.info("Scraped %d articles from %s", len(articles), source["name"])
        return articles

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
