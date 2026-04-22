from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from ..config.settings import AppConfig
from ..sources.rss import RSSFetcher
from ..sources.nitter import NitterFetcher
from ..sources.web_scraper import WebScraperFetcher
from ..storage.database import Database
from ..storage import queries
from ..processing.dedup import normalize_url, compute_content_hash, titles_are_similar
from ..processing.scorer import compute_score
from ..processing.llm import LLMProcessor

logger = logging.getLogger(__name__)

LLM_MAX_RETRIES = 5


def _chunk(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


class Pipeline:
    def __init__(self, db: Database, llm: LLMProcessor, config: AppConfig):
        self._db = db
        self._llm = llm
        self._config = config
        self._rss_fetcher = RSSFetcher()
        self._nitter_fetcher = NitterFetcher()
        self._web_scraper = WebScraperFetcher()

    async def run_fetch_cycle(self) -> dict:
        stats = {"fetched": 0, "new": 0, "duplicates": 0, "processed": 0, "retried": 0, "errors": 0}

        # TIER 1: Fetch + Dedup + Score
        recent = await queries.get_recent_titles(self._db, hours=48)
        self._recent_titles = [(r["title"], r["source_name"]) for r in recent]

        sources = await queries.get_active_sources(self._db)
        for source in sources:
            try:
                articles = await self._fetch_with_retry(source)
                stats["fetched"] += len(articles)

                for article in articles:
                    inserted = await self._tier1_process(article, source)
                    if inserted:
                        stats["new"] += 1
                    else:
                        stats["duplicates"] += 1

                await queries.update_source_fetched(self._db, source["id"], success=True)
            except Exception as e:
                logger.error("Error fetching %s: %s", source["name"], e)
                await queries.update_source_fetched(self._db, source["id"], success=False)
                stats["errors"] += 1

        # Disable sources with too many errors
        broken = await queries.disable_broken_sources(self._db)
        if broken:
            logger.warning("Disabled broken sources: %s", broken)

        # TIER 2: LLM Processing (new articles)
        if self._llm.daily_calls < self._config.llm.max_daily_calls:
            processed = await self._tier2_process()
            stats["processed"] = processed

        # TIER 3: Retry previously failed articles (with remaining daily budget)
        if self._llm.daily_calls < self._config.llm.max_daily_calls:
            retried = await self._tier3_retry_failed()
            stats["retried"] = retried

        logger.info(
            "Fetch cycle: fetched=%d new=%d dupes=%d processed=%d retried=%d errors=%d",
            stats["fetched"], stats["new"], stats["duplicates"],
            stats["processed"], stats["retried"], stats["errors"],
        )
        return stats

    async def _fetch_with_retry(self, source: dict, retries: int = 2):
        for attempt in range(retries):
            try:
                return await self._fetch_source(source)
            except Exception:
                if attempt < retries - 1:
                    await asyncio.sleep(5)
                else:
                    raise

    async def _fetch_source(self, source: dict):
        feed_type = source["feed_type"]
        if feed_type == "rss":
            return await self._rss_fetcher.fetch(source)
        elif feed_type == "nitter":
            return await self._nitter_fetcher.fetch(source)
        elif feed_type == "web_scraper":
            return await self._web_scraper.fetch(source)
        return []

    async def _tier1_process(self, article, source: dict) -> bool:
        # Hard filter: skip articles older than 48 hours
        if article.published_at:
            from datetime import timezone
            pub = article.published_at if article.published_at.tzinfo else article.published_at.replace(tzinfo=timezone.utc)
            age_hours = (datetime.now(timezone.utc) - pub).total_seconds() / 3600
            if age_hours > 48:
                return False

        # Semantic dedup: skip if a similar title already exists
        for existing_title, _ in getattr(self, "_recent_titles", []):
            if titles_are_similar(article.title, existing_title):
                logger.debug(
                    "Semantic dedup: '%s' ~ '%s'",
                    article.title[:60], existing_title[:60],
                )
                return False

        url_norm = normalize_url(article.url)
        content_hash = compute_content_hash(article.title, article.content)

        # Score
        score = compute_score(
            source_priority=source.get("priority", "low"),
            published_at=article.published_at,
            config=self._config.scoring,
        )

        # Atomic INSERT OR IGNORE handles dedup
        result = await queries.insert_article(
            db=self._db,
            url=article.url,
            url_normalized=url_norm,
            content_hash=content_hash,
            title=article.title,
            content_raw=article.content,
            source_id=source["id"],
            source_name=article.source_name,
            importance_score=score,
            published_at=article.published_at.isoformat() if article.published_at else None,
            image_url=getattr(article, "image_url", None),
        )

        if result is not None:
            if hasattr(self, "_recent_titles"):
                self._recent_titles.append((article.title, article.source_name))

        return result is not None

    async def _tier2_process(self) -> int:
        unprocessed = await queries.get_unprocessed_articles(
            self._db, limit=self._config.llm.batch_size * 10,
        )

        if not unprocessed:
            return 0

        return await self._process_articles(unprocessed)

    async def _tier3_retry_failed(self) -> int:
        """Retry articles that previously failed LLM processing (but haven't hit max retries)."""
        failed = await queries.get_retryable_failed_articles(
            self._db,
            max_fail_count=LLM_MAX_RETRIES,
            limit=self._config.llm.batch_size * 3,
        )

        if not failed:
            return 0

        logger.info("Retrying %d previously failed articles", len(failed))
        return await self._process_articles(failed)

    async def _process_articles(self, articles: list[dict]) -> int:
        """Common processing logic for both new and retry articles."""
        total_processed = 0
        for i, batch in enumerate(_chunk(articles, self._config.llm.batch_size)):
            if self._llm.daily_calls >= self._config.llm.max_daily_calls:
                logger.warning("Daily LLM call limit reached (%d)", self._config.llm.max_daily_calls)
                break

            # Rate limit: pause between API calls (free tier, 429 mitigation)
            if i > 0:
                await asyncio.sleep(30)

            results = await self._llm.summarize_batch(
                batch,
                max_tokens=self._config.llm.max_tokens_summarize,
            )

            # Track which articles got results
            matched_ids = set()
            for result in results:
                idx = result["article_index"] - 1
                if 0 <= idx < len(batch):
                    article = batch[idx]
                    matched_ids.add(article["id"])
                    await queries.update_article_processed(
                        db=self._db,
                        article_id=article["id"],
                        summary_ru=result["summary_ru"],
                        tags=result["tags"],
                        importance_score=result["importance"],
                        title_ru=result.get("title_ru", ""),
                    )
                    total_processed += 1

            # Handle articles that got no LLM result
            for article in batch:
                if article["id"] not in matched_ids:
                    fail_count = await queries.increment_llm_fail(self._db, article["id"])
                    if fail_count >= LLM_MAX_RETRIES:
                        await queries.mark_article_llm_failed(self._db, article["id"])
                        logger.warning(
                            "Article %d marked as LLM-failed after %d attempts: %s",
                            article["id"], fail_count, article.get("title", "")[:80],
                        )

        return total_processed

    async def close(self) -> None:
        await self._rss_fetcher.close()
        await self._nitter_fetcher.close()
        await self._web_scraper.close()
