SCHEMA_VERSION = 5

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    url TEXT NOT NULL,
    feed_type TEXT NOT NULL,
    category TEXT,
    priority TEXT DEFAULT 'low',
    last_fetched_at TEXT,
    last_successful_at TEXT,
    error_count INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL,
    url_normalized TEXT NOT NULL,
    content_hash TEXT,
    title TEXT NOT NULL,
    title_ru TEXT,
    content_raw TEXT,
    summary_ru TEXT,
    tags TEXT,
    source_id INTEGER NOT NULL REFERENCES sources(id),
    source_name TEXT NOT NULL,
    importance_score INTEGER DEFAULT 5,
    published_at TEXT,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    processed_at TEXT,
    sent_digest INTEGER DEFAULT 0,
    sent_instant INTEGER DEFAULT 0,
    llm_fail_count INTEGER DEFAULT 0,
    image_url TEXT,
    UNIQUE(url_normalized)
);

CREATE INDEX IF NOT EXISTS idx_articles_fetched ON articles(fetched_at);
CREATE INDEX IF NOT EXISTS idx_articles_importance ON articles(importance_score);
CREATE INDEX IF NOT EXISTS idx_articles_digest ON articles(sent_digest, processed_at);
CREATE INDEX IF NOT EXISTS idx_articles_content_hash ON articles(content_hash);

CREATE TABLE IF NOT EXISTS subscribers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL UNIQUE,
    username TEXT,
    first_name TEXT,
    language_code TEXT DEFAULT 'ru',
    tag_filter TEXT,
    instant_enabled INTEGER DEFAULT 1,
    digest_enabled INTEGER DEFAULT 1,
    digest_time TEXT DEFAULT '09:00',
    subscribed_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_digest_at TEXT,
    instant_count_today INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1
);
"""
