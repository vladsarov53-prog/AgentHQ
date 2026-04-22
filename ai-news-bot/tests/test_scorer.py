from datetime import datetime, timezone, timedelta

from src.processing.scorer import compute_score
from src.config.settings import ScoringConfig


def _config():
    return ScoringConfig()


class TestComputeScore:
    def test_base_score_with_low_priority(self):
        score = compute_score("low", None, _config())
        assert score == 2  # 1 base + 1 low

    def test_high_priority(self):
        score = compute_score("high", None, _config())
        assert score == 4  # 1 base + 3 high

    def test_medium_priority(self):
        score = compute_score("medium", None, _config())
        assert score == 3  # 1 base + 2 medium

    def test_fresh_recency_bonus(self):
        now = datetime.now(timezone.utc)
        published = now - timedelta(hours=2)  # < 6 hours (fresh)
        score = compute_score("low", published, _config())
        assert score == 4  # 1 + 1 + 2 fresh

    def test_recent_recency_bonus(self):
        now = datetime.now(timezone.utc)
        published = now - timedelta(hours=12)  # < 24 hours (recent)
        score = compute_score("low", published, _config())
        assert score == 3  # 1 + 1 + 1 recent

    def test_old_no_recency_bonus(self):
        published = datetime.now(timezone.utc) - timedelta(hours=48)
        score = compute_score("low", published, _config())
        assert score == 2  # 1 + 1, no recency

    def test_max_score_capped_at_10(self):
        published = datetime.now(timezone.utc) - timedelta(hours=1)
        score = compute_score("high", published, _config())
        assert score <= 10

    def test_naive_datetime_handled(self):
        published = datetime.now() - timedelta(hours=2)  # naive, no tzinfo
        score = compute_score("low", published, _config())
        assert score >= 2  # should not crash
