"""Tests for LLM module: Circuit Breaker, JSON parsing, fallback logic."""
import time
from unittest.mock import patch

from src.processing.llm import (
    CircuitBreaker,
    CircuitState,
    _extract_json_array,
    _fix_common_json_errors,
    _parse_llm_json,
)


class TestCircuitBreaker:
    def test_starts_closed(self):
        cb = CircuitBreaker()
        assert cb.state == CircuitState.CLOSED
        assert not cb.is_open

    def test_stays_closed_on_success(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_success()
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_opens_after_threshold_failures(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_success_resets_failure_count(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED

    def test_transitions_to_half_open_after_cooldown(self):
        cb = CircuitBreaker(failure_threshold=2, cooldown_seconds=0.1)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        time.sleep(0.15)
        assert cb.state == CircuitState.HALF_OPEN

    def test_half_open_closes_on_success(self):
        cb = CircuitBreaker(failure_threshold=2, cooldown_seconds=0.1)
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.15)
        assert cb.state == CircuitState.HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_half_open_reopens_on_failure(self):
        cb = CircuitBreaker(failure_threshold=2, cooldown_seconds=0.1)
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.15)
        assert cb.state == CircuitState.HALF_OPEN
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_stats(self):
        cb = CircuitBreaker(failure_threshold=5)
        cb.record_success()
        cb.record_success()
        cb.record_failure()
        stats = cb.stats
        assert stats["total_calls"] == 3
        assert stats["total_failures"] == 1
        assert stats["consecutive_failures"] == 1
        assert stats["success_rate_pct"] == round(2 / 3 * 100, 1)

    def test_reset(self):
        cb = CircuitBreaker(failure_threshold=2)
        cb.record_failure()
        cb.record_failure()
        assert cb.is_open
        cb.reset()
        assert cb.state == CircuitState.CLOSED


class TestExtractJsonArray:
    def test_simple_array(self):
        text = '[{"a": 1}, {"b": 2}]'
        assert _extract_json_array(text) == text

    def test_with_preamble(self):
        text = 'Here is the result:\n[{"a": 1}]\nDone.'
        assert _extract_json_array(text) == '[{"a": 1}]'

    def test_nested_arrays(self):
        text = '[{"tags": ["a", "b"]}, {"tags": ["c"]}]'
        result = _extract_json_array(text)
        assert result == text

    def test_no_array(self):
        assert _extract_json_array("no json here") is None

    def test_strings_with_brackets(self):
        text = '[{"title": "Test [D] post", "tags": ["models"]}]'
        result = _extract_json_array(text)
        assert result == text

    def test_unbalanced_returns_none(self):
        text = '[{"a": 1}, {"b": 2}'
        assert _extract_json_array(text) is None


class TestFixCommonJsonErrors:
    def test_trailing_comma_in_array(self):
        text = '[{"a": 1}, {"b": 2},]'
        assert _fix_common_json_errors(text) == '[{"a": 1}, {"b": 2}]'

    def test_trailing_comma_in_object(self):
        text = '{"a": 1, "b": 2,}'
        assert _fix_common_json_errors(text) == '{"a": 1, "b": 2}'

    def test_no_changes_needed(self):
        text = '[{"a": 1}]'
        assert _fix_common_json_errors(text) == text


class TestParseLlmJson:
    def test_valid_json_array(self):
        text = '[{"article_index": 1, "title_ru": "Test", "summary_ru": "Summary", "tags": ["models"], "importance": 7, "why_matters": ""}]'
        result = _parse_llm_json(text)
        assert len(result) == 1
        assert result[0]["article_index"] == 1

    def test_json_in_code_fence(self):
        text = '```json\n[{"article_index": 1, "title_ru": "X"}]\n```'
        result = _parse_llm_json(text)
        assert len(result) == 1

    def test_json_with_preamble(self):
        text = 'Here are the results:\n[{"article_index": 1, "title_ru": "X"}]'
        result = _parse_llm_json(text)
        assert len(result) == 1

    def test_trailing_comma(self):
        text = '[{"article_index": 1, "title_ru": "X",},]'
        result = _parse_llm_json(text)
        assert len(result) == 1

    def test_dict_wrapper(self):
        text = '{"articles": [{"article_index": 1, "title_ru": "X"}]}'
        result = _parse_llm_json(text)
        assert len(result) == 1

    def test_individual_objects_fallback(self):
        # Completely broken array but valid individual objects
        text = '{"article_index": 1, "title_ru": "A"}\n{"article_index": 2, "title_ru": "B"}'
        result = _parse_llm_json(text)
        assert len(result) == 2

    def test_empty_response(self):
        assert _parse_llm_json("") == []

    def test_completely_invalid(self):
        assert _parse_llm_json("This is not JSON at all") == []

    def test_reasoning_tags_stripped(self):
        text = '<thinking>Let me analyze...</thinking>\n[{"article_index": 1, "title_ru": "X"}]'
        result = _parse_llm_json(text)
        assert len(result) == 1
