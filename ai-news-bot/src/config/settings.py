from __future__ import annotations

import os
import yaml
from pathlib import Path
from dataclasses import dataclass, field
from dotenv import load_dotenv
from pydantic_settings import BaseSettings

# Load .env with override=True so file values beat empty system env vars
_env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(_env_path, override=True)


class EnvSettings(BaseSettings):
    telegram_bot_token: str
    gemini_api_key: str
    admin_telegram_id: int


@dataclass
class TagConfig:
    id: str
    label: str
    keywords: list[str]


@dataclass
class SourceConfig:
    name: str
    url: str
    feed_type: str
    priority: str = "low"
    category: str = ""


@dataclass
class ScoringConfig:
    source_priority: dict[str, int] = field(default_factory=lambda: {"high": 3, "medium": 2, "low": 1})
    recency_fresh_hours: int = 6
    recency_fresh_bonus: int = 2
    recency_recent_hours: int = 24
    recency_recent_bonus: int = 1
    multi_source_threshold: int = 3
    multi_source_bonus: int = 2
    max_per_source_in_digest: int = 3


@dataclass
class LLMConfig:
    summarize_model: str = "gemini-2.0-flash"
    digest_model: str = "gemini-2.0-flash"
    fallback_model: str = "gemini-2.0-flash-lite"
    max_tokens_summarize: int = 1024
    max_tokens_digest: int = 4096
    batch_size: int = 5
    max_daily_calls: int = 300


@dataclass
class BotConfig:
    digest_time: str = "09:00"
    timezone: str = "Europe/Moscow"
    fetch_interval_minutes: int = 45
    instant_threshold: int = 8
    max_articles_per_digest: int = 20
    max_instant_per_day: int = 1
    language: str = "ru"


@dataclass
class AppConfig:
    bot: BotConfig
    llm: LLMConfig
    scoring: ScoringConfig
    tags: list[TagConfig]
    sources: list[SourceConfig]


def load_yaml_config(path: Path | None = None) -> AppConfig:
    if path is None:
        path = Path(__file__).parent.parent.parent / "config.yaml"

    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    bot_raw = raw.get("bot", {})
    bot = BotConfig(
        digest_time=bot_raw.get("digest_time", "09:00"),
        timezone=bot_raw.get("timezone", "Europe/Moscow"),
        fetch_interval_minutes=bot_raw.get("fetch_interval_minutes", 45),
        instant_threshold=bot_raw.get("instant_threshold", 8),
        max_articles_per_digest=bot_raw.get("max_articles_per_digest", 20),
        max_instant_per_day=bot_raw.get("max_instant_per_day", 1),
        language=bot_raw.get("language", "ru"),
    )

    llm_raw = raw.get("llm", {})
    llm = LLMConfig(
        summarize_model=llm_raw.get("summarize_model", LLMConfig.summarize_model),
        digest_model=llm_raw.get("digest_model", LLMConfig.digest_model),
        fallback_model=llm_raw.get("fallback_model", LLMConfig.fallback_model),
        max_tokens_summarize=llm_raw.get("max_tokens_summarize", 1024),
        max_tokens_digest=llm_raw.get("max_tokens_digest", 4096),
        batch_size=llm_raw.get("batch_size", 5),
        max_daily_calls=llm_raw.get("max_daily_calls", 300),
    )

    scoring_raw = raw.get("scoring", {})
    recency = scoring_raw.get("recency", {})
    default_priority = {"high": 3, "medium": 2, "low": 1}
    scoring = ScoringConfig(
        source_priority=scoring_raw.get("source_priority", default_priority),
        recency_fresh_hours=recency.get("fresh_hours", 6),
        recency_fresh_bonus=recency.get("fresh_bonus", 2),
        recency_recent_hours=recency.get("recent_hours", 24),
        recency_recent_bonus=recency.get("recent_bonus", 1),
        multi_source_threshold=scoring_raw.get("multi_source_threshold", 3),
        multi_source_bonus=scoring_raw.get("multi_source_bonus", 2),
        max_per_source_in_digest=scoring_raw.get("max_per_source_in_digest", 3),
    )

    tags = [
        TagConfig(id=t["id"], label=t["label"], keywords=t.get("keywords", []))
        for t in raw.get("tags", [])
    ]

    sources = []
    for category, source_list in raw.get("sources", {}).items():
        for s in source_list:
            sources.append(SourceConfig(
                name=s["name"],
                url=s["url"],
                feed_type=s["feed_type"],
                priority=s.get("priority", "low"),
                category=category,
            ))

    return AppConfig(bot=bot, llm=llm, scoring=scoring, tags=tags, sources=sources)
