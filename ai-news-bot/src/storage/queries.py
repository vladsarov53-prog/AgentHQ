from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from .database import Database

logger = logging.getLogger(__name__)


async def sync_sources(db: Database, sources: list) -> None:
    for src in sources:
        await db.conn.execute(
            """INSERT INTO sources (name, url, feed_type, category, priority)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(name) DO UPDATE SET
                 url=excluded.url,
                 feed_type=excluded.feed_type,
                 category=excluded.category,
                 priority=excluded.priority""",
            (src.name, src.url, src.feed_type, src.category, src.priority),
        )
    await db.conn.commit()


async def get_active_sources(db: Database) -> list[dict]:
    cursor = await db.conn.execute(
        "SELECT * FROM sources WHERE is_active = 1"
    )
    return [dict(row) for row in await cursor.fetchall()]


async def url_exists(db: Database, url_normalized: str) -> bool:
    cursor = await db.conn.execute(
        "SELECT 1 FROM articles WHERE url_normalized = ?", (url_normalized,)
    )
    return await cursor.fetchone() is not None


async def hash_exists(db: Database, content_hash: str) -> bool:
    cursor = await db.conn.execute(
        "SELECT 1 FROM articles WHERE content_hash = ?", (content_hash,)
    )
    return await cursor.fetchone() is not None


async def get_recent_titles(db: Database, hours: int = 48) -> list[dict]:
    """Get titles of recent articles for semantic dedup."""
    cursor = await db.conn.execute(
        """SELECT id, title, source_name, importance_score
           FROM articles
           WHERE fetched_at >= datetime('now', ? || ' hours')""",
        (f"-{hours}",),
    )
    return [dict(row) for row in await cursor.fetchall()]


async def insert_article(
    db: Database,
    url: str,
    url_normalized: str,
    content_hash: str,
    title: str,
    content_raw: str,
    source_id: int,
    source_name: str,
    importance_score: int = 5,
    published_at: str | None = None,
    image_url: str | None = None,
) -> int | None:
    cursor = await db.conn.execute(
        """INSERT OR IGNORE INTO articles
           (url, url_normalized, content_hash, title, content_raw,
            source_id, source_name, importance_score, published_at, image_url)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (url, url_normalized, content_hash, title, content_raw,
         source_id, source_name, importance_score, published_at, image_url),
    )
    await db.conn.commit()
    if cursor.rowcount > 0:
        return cursor.lastrowid
    return None


async def get_unprocessed_articles(db: Database, limit: int = 50) -> list[dict]:
    # Get top N per source for diversity, then round-robin
    cursor = await db.conn.execute(
        "SELECT DISTINCT source_id FROM articles WHERE processed_at IS NULL"
    )
    source_ids = [row["source_id"] for row in await cursor.fetchall()]

    by_source: dict[int, list] = {}
    per_source = max(3, limit // max(len(source_ids), 1))
    for sid in source_ids:
        cursor = await db.conn.execute(
            """SELECT * FROM articles
               WHERE processed_at IS NULL AND source_id = ?
               ORDER BY fetched_at ASC LIMIT ?""",
            (sid, per_source),
        )
        by_source[sid] = [dict(row) for row in await cursor.fetchall()]

    # Round-robin
    mixed: list[dict] = []
    iterators = {sid: iter(rows) for sid, rows in by_source.items()}
    while len(mixed) < limit and iterators:
        exhausted = []
        for sid in list(iterators):
            if len(mixed) >= limit:
                break
            try:
                mixed.append(next(iterators[sid]))
            except StopIteration:
                exhausted.append(sid)
        for sid in exhausted:
            del iterators[sid]

    return mixed


async def update_article_processed(
    db: Database,
    article_id: int,
    summary_ru: str,
    tags: list[str],
    importance_score: int,
    title_ru: str = "",
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    await db.conn.execute(
        """UPDATE articles
           SET summary_ru = ?, tags = ?, importance_score = ?, title_ru = ?, processed_at = ?
           WHERE id = ?""",
        (summary_ru, json.dumps(tags, ensure_ascii=False), importance_score, title_ru, now, article_id),
    )
    await db.conn.commit()


async def get_unsent_instant(db: Database, threshold: int = 8) -> list[dict]:
    cursor = await db.conn.execute(
        """SELECT * FROM articles
           WHERE processed_at IS NOT NULL
             AND sent_instant = 0
             AND importance_score >= ?
           ORDER BY importance_score DESC""",
        (threshold,),
    )
    return [dict(row) for row in await cursor.fetchall()]


async def mark_sent_instant(db: Database, article_id: int) -> None:
    await db.conn.execute(
        "UPDATE articles SET sent_instant = 1 WHERE id = ?", (article_id,)
    )
    await db.conn.commit()


async def get_digest_articles(
    db: Database, hours: int = 24, limit: int = 20
) -> list[dict]:
    cursor = await db.conn.execute(
        """SELECT * FROM articles
           WHERE processed_at IS NOT NULL
             AND sent_digest = 0
             AND fetched_at >= datetime('now', ? || ' hours')
           ORDER BY importance_score DESC
           LIMIT ?""",
        (f"-{hours}", limit),
    )
    return [dict(row) for row in await cursor.fetchall()]


async def mark_sent_digest(db: Database, article_ids: list[int]) -> None:
    if not article_ids:
        return
    placeholders = ",".join("?" * len(article_ids))
    await db.conn.execute(
        f"UPDATE articles SET sent_digest = 1 WHERE id IN ({placeholders})",
        article_ids,
    )
    await db.conn.commit()


async def upsert_subscriber(
    db: Database,
    telegram_id: int,
    username: str | None = None,
    first_name: str | None = None,
) -> None:
    await db.conn.execute(
        """INSERT INTO subscribers (telegram_id, username, first_name)
           VALUES (?, ?, ?)
           ON CONFLICT(telegram_id) DO UPDATE SET
             username=excluded.username,
             first_name=excluded.first_name,
             is_active=1""",
        (telegram_id, username, first_name),
    )
    await db.conn.commit()


async def get_active_subscribers(db: Database) -> list[dict]:
    cursor = await db.conn.execute(
        "SELECT * FROM subscribers WHERE is_active = 1"
    )
    return [dict(row) for row in await cursor.fetchall()]


async def get_instant_subscribers(db: Database, max_per_day: int = 0) -> list[dict]:
    if max_per_day > 0:
        cursor = await db.conn.execute(
            """SELECT * FROM subscribers
               WHERE is_active = 1 AND instant_enabled = 1
                 AND instant_count_today < ?""",
            (max_per_day,),
        )
    else:
        cursor = await db.conn.execute(
            "SELECT * FROM subscribers WHERE is_active = 1 AND instant_enabled = 1"
        )
    return [dict(row) for row in await cursor.fetchall()]


async def increment_instant_count(db: Database, telegram_id: int) -> None:
    await db.conn.execute(
        "UPDATE subscribers SET instant_count_today = instant_count_today + 1 WHERE telegram_id = ?",
        (telegram_id,),
    )
    await db.conn.commit()


async def reset_instant_counts(db: Database) -> None:
    await db.conn.execute("UPDATE subscribers SET instant_count_today = 0")
    await db.conn.commit()


async def get_digest_subscribers(db: Database) -> list[dict]:
    cursor = await db.conn.execute(
        "SELECT * FROM subscribers WHERE is_active = 1 AND digest_enabled = 1"
    )
    return [dict(row) for row in await cursor.fetchall()]


async def update_subscriber_settings(
    db: Database,
    telegram_id: int,
    instant_enabled: bool | None = None,
    digest_enabled: bool | None = None,
    tag_filter: list[str] | None = None,
) -> None:
    updates = []
    params: list = []
    if instant_enabled is not None:
        updates.append("instant_enabled = ?")
        params.append(int(instant_enabled))
    if digest_enabled is not None:
        updates.append("digest_enabled = ?")
        params.append(int(digest_enabled))
    if tag_filter is not None:
        updates.append("tag_filter = ?")
        params.append(json.dumps(tag_filter, ensure_ascii=False))

    if updates:
        params.append(telegram_id)
        await db.conn.execute(
            f"UPDATE subscribers SET {', '.join(updates)} WHERE telegram_id = ?",
            params,
        )
        await db.conn.commit()


async def deactivate_subscriber(db: Database, telegram_id: int) -> None:
    await db.conn.execute(
        "UPDATE subscribers SET is_active = 0 WHERE telegram_id = ?",
        (telegram_id,),
    )
    await db.conn.commit()


async def update_source_fetched(
    db: Database, source_id: int, success: bool
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    if success:
        await db.conn.execute(
            """UPDATE sources
               SET last_fetched_at = ?, last_successful_at = ?, error_count = 0
               WHERE id = ?""",
            (now, now, source_id),
        )
    else:
        await db.conn.execute(
            """UPDATE sources
               SET last_fetched_at = ?, error_count = error_count + 1
               WHERE id = ?""",
            (now, source_id),
        )
    await db.conn.commit()


async def disable_broken_sources(db: Database, max_errors: int = 10) -> list[str]:
    cursor = await db.conn.execute(
        "SELECT name FROM sources WHERE error_count >= ? AND is_active = 1",
        (max_errors,),
    )
    broken = [row["name"] for row in await cursor.fetchall()]
    if broken:
        await db.conn.execute(
            "UPDATE sources SET is_active = 0 WHERE error_count >= ?",
            (max_errors,),
        )
        await db.conn.commit()
    return broken


async def get_stats(db: Database) -> dict:
    result = {}
    cursor = await db.conn.execute("SELECT COUNT(*) as c FROM articles")
    result["total_articles"] = (await cursor.fetchone())["c"]

    cursor = await db.conn.execute(
        "SELECT COUNT(*) as c FROM articles WHERE processed_at IS NOT NULL"
    )
    result["processed_articles"] = (await cursor.fetchone())["c"]

    cursor = await db.conn.execute(
        "SELECT COUNT(*) as c FROM subscribers WHERE is_active = 1"
    )
    result["active_subscribers"] = (await cursor.fetchone())["c"]

    cursor = await db.conn.execute(
        "SELECT COUNT(*) as c FROM sources WHERE is_active = 1"
    )
    result["active_sources"] = (await cursor.fetchone())["c"]

    cursor = await db.conn.execute(
        "SELECT COUNT(*) as c FROM sources WHERE error_count > 0"
    )
    result["sources_with_errors"] = (await cursor.fetchone())["c"]

    return result


async def cleanup_old_articles(db: Database, days: int = 30) -> int:
    cursor = await db.conn.execute(
        "DELETE FROM articles WHERE fetched_at < datetime('now', ? || ' days')",
        (f"-{days}",),
    )
    await db.conn.commit()
    return cursor.rowcount


async def increment_llm_fail(db: Database, article_id: int) -> int:
    await db.conn.execute(
        "UPDATE articles SET llm_fail_count = COALESCE(llm_fail_count, 0) + 1 WHERE id = ?",
        (article_id,),
    )
    await db.conn.commit()
    cursor = await db.conn.execute(
        "SELECT llm_fail_count FROM articles WHERE id = ?", (article_id,),
    )
    row = await cursor.fetchone()
    return row["llm_fail_count"] if row else 0


async def mark_article_llm_failed(db: Database, article_id: int) -> None:
    now = datetime.now(timezone.utc).isoformat()
    await db.conn.execute(
        """UPDATE articles
           SET summary_ru = '[Не удалось обработать]', tags = '[]',
               importance_score = 1, processed_at = ?
           WHERE id = ?""",
        (now, article_id),
    )
    await db.conn.commit()


async def reset_llm_failed(db: Database) -> int:
    """Reset LLM-failed articles so they can be reprocessed."""
    cursor = await db.conn.execute(
        """UPDATE articles
           SET llm_fail_count = 0, processed_at = NULL,
               summary_ru = NULL, tags = NULL, importance_score = 5
           WHERE llm_fail_count >= 3"""
    )
    await db.conn.commit()
    return cursor.rowcount


async def get_health_status(db: Database) -> dict:
    result = {}

    # Stuck articles (unprocessed > 6 hours)
    cursor = await db.conn.execute(
        """SELECT COUNT(*) as c FROM articles
           WHERE processed_at IS NULL
             AND fetched_at < datetime('now', '-6 hours')"""
    )
    result["stuck_articles"] = (await cursor.fetchone())["c"]

    # Unprocessed total
    cursor = await db.conn.execute(
        "SELECT COUNT(*) as c FROM articles WHERE processed_at IS NULL"
    )
    result["unprocessed"] = (await cursor.fetchone())["c"]

    # Sources not fetched in 3 hours
    cursor = await db.conn.execute(
        """SELECT COUNT(*) as c FROM sources
           WHERE is_active = 1
             AND (last_fetched_at IS NULL OR last_fetched_at < datetime('now', '-3 hours'))"""
    )
    result["stale_sources"] = (await cursor.fetchone())["c"]

    # Sources with errors
    cursor = await db.conn.execute(
        "SELECT COUNT(*) as c FROM sources WHERE error_count > 0"
    )
    result["error_sources"] = (await cursor.fetchone())["c"]

    # Articles processed last 24h
    cursor = await db.conn.execute(
        """SELECT COUNT(*) as c FROM articles
           WHERE processed_at IS NOT NULL
             AND processed_at >= datetime('now', '-24 hours')"""
    )
    result["processed_24h"] = (await cursor.fetchone())["c"]

    # Last fetch time
    cursor = await db.conn.execute(
        "SELECT MAX(last_fetched_at) as t FROM sources"
    )
    row = await cursor.fetchone()
    result["last_fetch"] = row["t"] if row else None

    # LLM failed articles (only last 7 days to avoid stale accumulation)
    cursor = await db.conn.execute(
        """SELECT COUNT(*) as c FROM articles
           WHERE llm_fail_count >= 3
             AND fetched_at >= datetime('now', '-7 days')"""
    )
    result["llm_failed"] = (await cursor.fetchone())["c"]

    return result
