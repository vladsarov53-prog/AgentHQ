from __future__ import annotations

from datetime import datetime, timezone

from ..config.settings import ScoringConfig


def compute_score(
    source_priority: str,
    published_at: datetime | None,
    config: ScoringConfig,
) -> int:
    score = 1  # base

    # Source bonus
    bonus = config.source_priority.get(source_priority, 1)
    score += bonus

    # Recency bonus
    if published_at:
        now = datetime.now(timezone.utc)
        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=timezone.utc)
        age_hours = (now - published_at).total_seconds() / 3600

        if age_hours < config.recency_fresh_hours:
            score += config.recency_fresh_bonus
        elif age_hours < config.recency_recent_hours:
            score += config.recency_recent_bonus

    return min(score, 10)
