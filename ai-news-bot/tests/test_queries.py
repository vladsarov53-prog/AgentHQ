import pytest
import pytest_asyncio

from src.storage.database import Database
from src.storage import queries


@pytest_asyncio.fixture
async def db(tmp_path):
    database = await Database.create(tmp_path / "test.db")
    # Insert a test source
    await database.conn.execute(
        "INSERT INTO sources (name, url, feed_type, category, priority) VALUES (?, ?, ?, ?, ?)",
        ("test_source", "https://example.com/rss", "rss", "test", "low"),
    )
    await database.conn.commit()
    yield database
    await database.close()


@pytest.mark.asyncio
async def test_insert_or_ignore_dedup(db):
    """Atomic INSERT OR IGNORE should handle duplicate URLs without exception."""
    result1 = await queries.insert_article(
        db, "https://example.com/1", "https://example.com/1",
        "hash1", "Title 1", "Content", 1, "test_source",
    )
    assert result1 is not None

    result2 = await queries.insert_article(
        db, "https://example.com/1", "https://example.com/1",
        "hash2", "Title 1 Copy", "Content", 1, "test_source",
    )
    assert result2 is None  # duplicate, ignored


@pytest.mark.asyncio
async def test_insert_different_urls(db):
    r1 = await queries.insert_article(
        db, "https://a.com/1", "https://a.com/1", "h1", "T1", "C", 1, "s",
    )
    r2 = await queries.insert_article(
        db, "https://b.com/2", "https://b.com/2", "h2", "T2", "C", 1, "s",
    )
    assert r1 is not None
    assert r2 is not None
    assert r1 != r2


@pytest.mark.asyncio
async def test_unprocessed_articles_round_robin(db):
    # Insert from source 1
    for i in range(5):
        await queries.insert_article(
            db, f"https://a.com/{i}", f"https://a.com/{i}",
            f"ha{i}", f"A{i}", "C", 1, "source_a",
        )
    # The round-robin should return them
    articles = await queries.get_unprocessed_articles(db, limit=3)
    assert len(articles) == 3


@pytest.mark.asyncio
async def test_llm_fail_tracking(db):
    article_id = await queries.insert_article(
        db, "https://test.com/fail", "https://test.com/fail",
        "hfail", "Fail Article", "Content", 1, "test",
    )
    assert article_id is not None

    count = await queries.increment_llm_fail(db, article_id)
    assert count == 1

    count = await queries.increment_llm_fail(db, article_id)
    assert count == 2

    count = await queries.increment_llm_fail(db, article_id)
    assert count == 3

    # Mark as failed
    await queries.mark_article_llm_failed(db, article_id)

    cursor = await db.conn.execute("SELECT * FROM articles WHERE id = ?", (article_id,))
    row = await cursor.fetchone()
    assert row["processed_at"] is not None
    assert row["importance_score"] == 1
    assert row["summary_ru"] == "[Не удалось обработать]"


@pytest.mark.asyncio
async def test_retryable_failed_articles(db):
    """Articles with 1-4 fail count should be retryable, 5+ should not."""
    # Create articles with different fail counts
    for i in range(5):
        aid = await queries.insert_article(
            db, f"https://retry.com/{i}", f"https://retry.com/{i}",
            f"hretry{i}", f"Retry {i}", "Content", 1, "test",
        )
        for _ in range(i + 1):
            await queries.increment_llm_fail(db, aid)

    # fail counts: 1, 2, 3, 4, 5
    # retryable (< 5): 4 articles
    retryable = await queries.get_retryable_failed_articles(db, max_fail_count=5, limit=10)
    assert len(retryable) == 4
    # Should be ordered by fail_count ASC
    assert retryable[0]["llm_fail_count"] == 1

    # With max_fail_count=3, only 2 articles retryable (fail_count 1 and 2)
    retryable2 = await queries.get_retryable_failed_articles(db, max_fail_count=3, limit=10)
    assert len(retryable2) == 2


@pytest.mark.asyncio
async def test_health_status(db):
    health = await queries.get_health_status(db)
    assert "stuck_articles" in health
    assert "unprocessed" in health
    assert "stale_sources" in health
    assert "error_sources" in health
    assert "processed_24h" in health
    assert "llm_failed" in health


@pytest.mark.asyncio
async def test_schema_version(db):
    cursor = await db.conn.execute("SELECT MAX(version) as v FROM schema_version")
    row = await cursor.fetchone()
    assert row["v"] == 5
