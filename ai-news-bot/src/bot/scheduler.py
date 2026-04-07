from __future__ import annotations

import json
import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot

from ..config.settings import AppConfig
from ..processing.pipeline import Pipeline
from ..processing.llm import LLMProcessor
from ..processing.prompts import SYSTEM_PROMPT_DIGEST
from ..storage.database import Database
from ..storage import queries
from .formatter import format_digest, format_digest_cards, format_instant

logger = logging.getLogger(__name__)

_ALERT_THRESHOLD = 3
_failure_counts: dict[str, int] = {}


async def _alert_admin(bot: Bot, admin_id: int, job_name: str, error: Exception) -> None:
    count = _failure_counts.get(job_name, 0)
    if count >= _ALERT_THRESHOLD and count % _ALERT_THRESHOLD == 0:
        try:
            await bot.send_message(
                admin_id,
                f"ALERT: {job_name} failed {count} times consecutively.\n"
                f"Last error: {str(error)[:200]}",
            )
        except Exception as e:
            logger.error("Failed to send admin alert: %s", e)


def setup_scheduler(
    db: Database,
    bot: Bot,
    pipeline: Pipeline,
    llm: LLMProcessor,
    config: AppConfig,
    admin_id: int = 0,
) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=config.bot.timezone)

    common_kwargs = {"db": db, "bot": bot, "admin_id": admin_id}

    # Fetch cycle
    scheduler.add_job(
        _fetch_and_dispatch,
        "interval",
        minutes=config.bot.fetch_interval_minutes,
        id="fetch_cycle",
        kwargs={**common_kwargs, "pipeline": pipeline, "config": config},
    )

    # Daily digest
    hour, minute = map(int, config.bot.digest_time.split(":"))
    scheduler.add_job(
        _send_daily_digest,
        "cron",
        hour=hour,
        minute=minute,
        id="daily_digest",
        kwargs={**common_kwargs, "llm": llm, "config": config},
    )

    # Cleanup old articles
    scheduler.add_job(
        _cleanup,
        "cron",
        hour=3,
        minute=0,
        id="cleanup",
        kwargs={"db": db},
    )

    # Reset daily LLM counter at midnight
    scheduler.add_job(
        _reset_counters,
        "cron",
        hour=0,
        minute=0,
        id="reset_counters",
        kwargs={"llm": llm, "db": db},
    )

    # Health check every 2 hours
    scheduler.add_job(
        _health_check,
        "interval",
        hours=2,
        id="health_check",
        kwargs=common_kwargs,
    )

    return scheduler


async def _fetch_and_dispatch(
    db: Database,
    bot: Bot,
    pipeline: Pipeline,
    config: AppConfig,
    admin_id: int = 0,
) -> None:
    try:
        result = await pipeline.run_fetch_cycle()
        logger.info("Fetch cycle completed: %s", result)
        _failure_counts["fetch_and_dispatch"] = 0

        # Dispatch instant notifications (respecting daily limit)
        threshold = config.bot.instant_threshold
        max_instant = config.bot.max_instant_per_day
        urgent = await queries.get_unsent_instant(db, threshold)

        if urgent:
            # Track sent count per subscriber in memory to enforce limit
            sent_count: dict[int, int] = {}
            subscribers = await queries.get_instant_subscribers(db, max_per_day=max_instant)
            for sub in subscribers:
                sent_count[sub["telegram_id"]] = sub.get("instant_count_today", 0)

            for article in urgent:
                text = format_instant(article)
                image_url = article.get("image_url")
                for sub in subscribers:
                    tid = sub["telegram_id"]
                    if sent_count.get(tid, 0) >= max_instant:
                        continue
                    if _matches_filter(article, sub):
                        try:
                            if image_url:
                                try:
                                    await bot.send_photo(
                                        tid,
                                        photo=image_url,
                                        caption=text,
                                        parse_mode="HTML",
                                    )
                                except Exception:
                                    await bot.send_message(
                                        tid,
                                        text,
                                        parse_mode="HTML",
                                        disable_web_page_preview=False,
                                    )
                            else:
                                await bot.send_message(
                                    tid,
                                    text,
                                    parse_mode="HTML",
                                    disable_web_page_preview=False,
                                )
                            sent_count[tid] = sent_count.get(tid, 0) + 1
                            await queries.increment_instant_count(db, tid)
                        except Exception as e:
                            logger.warning("Failed to send to %s: %s", tid, e)
                await queries.mark_sent_instant(db, article["id"])

    except Exception as e:
        logger.error("Fetch and dispatch error: %s", e)
        _failure_counts["fetch_and_dispatch"] = _failure_counts.get("fetch_and_dispatch", 0) + 1
        if admin_id:
            await _alert_admin(bot, admin_id, "fetch_and_dispatch", e)


async def _send_daily_digest(
    db: Database,
    bot: Bot,
    llm: LLMProcessor,
    config: AppConfig,
    admin_id: int = 0,
) -> None:
    try:
        articles = await queries.get_digest_articles(
            db, hours=24, limit=config.bot.max_articles_per_digest,
        )

        if not articles:
            logger.info("No articles for daily digest")
            return

        date_str = datetime.now().strftime("%d %B %Y")
        cards = format_digest_cards(articles, date_str)

        subscribers = await queries.get_digest_subscribers(db)
        for sub in subscribers:
            for card in cards:
                try:
                    await _send_card(bot, sub["telegram_id"], card)
                except Exception as e:
                    logger.warning("Failed to send digest to %s: %s", sub["telegram_id"], e)

        article_ids = [a["id"] for a in articles]
        await queries.mark_sent_digest(db, article_ids)
        logger.info("Daily digest sent to %d subscribers (%d articles)", len(subscribers), len(articles))
        _failure_counts["daily_digest"] = 0

    except Exception as e:
        logger.error("Daily digest error: %s", e)
        _failure_counts["daily_digest"] = _failure_counts.get("daily_digest", 0) + 1
        if admin_id:
            await _alert_admin(bot, admin_id, "daily_digest", e)


async def _cleanup(db: Database) -> None:
    try:
        deleted = await queries.cleanup_old_articles(db, days=30)
        if deleted:
            logger.info("Cleaned up %d old articles", deleted)
    except Exception as e:
        logger.error("Cleanup error: %s", e)


async def _reset_counters(llm: LLMProcessor, db: Database) -> None:
    llm.reset_daily_counter()
    await queries.reset_instant_counts(db)
    logger.info("Daily LLM and instant counters reset")


async def _health_check(db: Database, bot: Bot, admin_id: int = 0) -> None:
    try:
        health = await queries.get_health_status(db)
        issues = []

        if health["stuck_articles"] > 0:
            issues.append(f"Зависших статей (>6ч): {health['stuck_articles']}")
        if health["stale_sources"] > 0:
            issues.append(f"Источников без фетча (>3ч): {health['stale_sources']}")
        if health["error_sources"] > 0:
            issues.append(f"Источников с ошибками: {health['error_sources']}")
        if health["llm_failed"] > 5:
            issues.append(f"LLM-failed статей: {health['llm_failed']}")

        if issues and admin_id:
            text = "HEALTH CHECK:\n" + "\n".join(f"  {i}" for i in issues)
            try:
                await bot.send_message(admin_id, text)
            except Exception as e:
                logger.error("Failed to send health check: %s", e)

        logger.info(
            "Health: unprocessed=%d stuck=%d stale_sources=%d errors=%d processed_24h=%d",
            health["unprocessed"], health["stuck_articles"],
            health["stale_sources"], health["error_sources"], health["processed_24h"],
        )
    except Exception as e:
        logger.error("Health check error: %s", e)


async def _send_card(bot: Bot, chat_id: int, card) -> None:
    """Send a DigestCard as photo (if image_url exists) or text message."""
    if card.image_url:
        try:
            await bot.send_photo(
                chat_id,
                photo=card.image_url,
                caption=card.text,
                parse_mode="HTML",
            )
            return
        except Exception as e:
            # Image URL might be broken/expired, fall back to text
            logger.debug("send_photo failed (%s), falling back to text: %s", card.image_url, e)

    # Text-only fallback (or card without image)
    await bot.send_message(
        chat_id,
        card.text,
        parse_mode="HTML",
        disable_web_page_preview=False,  # allow Telegram link preview as fallback image
    )


def _matches_filter(article: dict, subscriber: dict) -> bool:
    tag_filter = subscriber.get("tag_filter")
    if not tag_filter:
        return True

    if isinstance(tag_filter, str):
        try:
            tag_filter = json.loads(tag_filter)
        except (json.JSONDecodeError, TypeError):
            return True

    if not tag_filter:
        return True

    article_tags = article.get("tags", "[]")
    if isinstance(article_tags, str):
        try:
            article_tags = json.loads(article_tags)
        except (json.JSONDecodeError, TypeError):
            article_tags = []

    return bool(set(article_tags) & set(tag_filter))
