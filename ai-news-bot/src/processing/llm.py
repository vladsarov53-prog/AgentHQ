from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from enum import Enum

from openai import AsyncOpenAI

from .prompts import SYSTEM_PROMPT_SUMMARIZE, build_summarize_user_prompt
from .sanitizer import sanitize_llm_output

logger = logging.getLogger(__name__)

VALID_TAGS = {
    "agentic", "llm_engineering", "models", "research", "products",
    "open_source", "safety", "mcp_a2a", "sapr_ai", "business",
}


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Circuit breaker pattern for LLM API calls.

    CLOSED: normal operation, requests go through.
    OPEN: too many failures, requests blocked for cooldown_seconds.
    HALF_OPEN: after cooldown, one probe request allowed.
    """

    def __init__(self, failure_threshold: int = 5, cooldown_seconds: float = 120.0):
        self._failure_threshold = failure_threshold
        self._cooldown_seconds = cooldown_seconds
        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._last_failure_time: float = 0.0
        self._total_calls = 0
        self._total_failures = 0

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN:
            elapsed = time.monotonic() - self._last_failure_time
            if elapsed >= self._cooldown_seconds:
                self._state = CircuitState.HALF_OPEN
                logger.info("Circuit breaker: OPEN -> HALF_OPEN (cooldown elapsed)")
        return self._state

    @property
    def is_open(self) -> bool:
        return self.state == CircuitState.OPEN

    @property
    def success_rate_pct(self) -> float:
        if self._total_calls == 0:
            return 100.0
        return (self._total_calls - self._total_failures) / self._total_calls * 100

    @property
    def stats(self) -> dict:
        return {
            "state": self.state.value,
            "consecutive_failures": self._consecutive_failures,
            "total_calls": self._total_calls,
            "total_failures": self._total_failures,
            "success_rate_pct": round(self.success_rate_pct, 1),
        }

    def record_success(self) -> None:
        self._total_calls += 1
        if self._state == CircuitState.HALF_OPEN:
            logger.info("Circuit breaker: HALF_OPEN -> CLOSED (probe succeeded)")
        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0

    def record_failure(self) -> None:
        self._total_calls += 1
        self._total_failures += 1
        self._consecutive_failures += 1
        self._last_failure_time = time.monotonic()

        if self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.OPEN
            logger.warning("Circuit breaker: HALF_OPEN -> OPEN (probe failed)")
        elif self._consecutive_failures >= self._failure_threshold:
            if self._state != CircuitState.OPEN:
                logger.warning(
                    "Circuit breaker: CLOSED -> OPEN (%d consecutive failures)",
                    self._consecutive_failures,
                )
            self._state = CircuitState.OPEN

    def reset(self) -> None:
        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0


def _extract_json_array(text: str) -> str | None:
    """Extract JSON array with proper bracket matching (handles nested arrays)."""
    start = text.find("[")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape_next = False
    for i in range(start, len(text)):
        c = text[i]
        if escape_next:
            escape_next = False
            continue
        if c == "\\":
            escape_next = True
            continue
        if c == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def _fix_common_json_errors(text: str) -> str:
    """Fix common LLM JSON mistakes: trailing commas, unescaped newlines in strings."""
    # Remove trailing commas before ] or }
    text = re.sub(r',\s*([}\]])', r'\1', text)
    return text


def _parse_llm_json(raw_text: str) -> list[dict]:
    """Robust JSON parsing with multiple fallback strategies."""
    cleaned = sanitize_llm_output(raw_text)

    # Strategy 1: extract proper JSON array with bracket matching
    json_str = _extract_json_array(cleaned)
    if json_str:
        json_str = _fix_common_json_errors(json_str)
        try:
            parsed = json.loads(json_str)
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass

    # Strategy 2: try the whole cleaned text
    cleaned_fixed = _fix_common_json_errors(cleaned)
    try:
        parsed = json.loads(cleaned_fixed)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            return parsed.get("articles", parsed.get("results", [parsed]))
    except json.JSONDecodeError:
        pass

    # Strategy 3: extract individual JSON objects and collect them
    objects = []
    for match in re.finditer(r'\{[^{}]*\}', cleaned):
        try:
            obj = json.loads(_fix_common_json_errors(match.group()))
            if isinstance(obj, dict) and "article_index" in obj:
                objects.append(obj)
        except json.JSONDecodeError:
            continue
    if objects:
        logger.warning("JSON fallback: extracted %d individual objects", len(objects))
        return objects

    logger.error("All JSON parsing strategies failed (len=%d): %.300s", len(cleaned), cleaned)
    return []


class LLMProcessor:
    def __init__(
        self,
        api_key: str,
        summarize_model: str,
        digest_model: str,
        fallback_model: str = "",
    ):
        self._client = AsyncOpenAI(
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            api_key=api_key,
        )
        self._summarize_model = summarize_model
        self._digest_model = digest_model
        self._fallback_model = fallback_model
        self._daily_calls = 0

        # Per-model circuit breakers
        self._breakers: dict[str, CircuitBreaker] = {
            summarize_model: CircuitBreaker(failure_threshold=5, cooldown_seconds=120),
        }
        if fallback_model:
            self._breakers[fallback_model] = CircuitBreaker(failure_threshold=5, cooldown_seconds=120)

    def _get_breaker(self, model: str) -> CircuitBreaker:
        if model not in self._breakers:
            self._breakers[model] = CircuitBreaker()
        return self._breakers[model]

    def _pick_model(self, preferred: str) -> str | None:
        """Pick an available model: preferred first, then fallback."""
        breaker = self._get_breaker(preferred)
        if not breaker.is_open:
            return preferred
        if self._fallback_model and self._fallback_model != preferred:
            fb_breaker = self._get_breaker(self._fallback_model)
            if not fb_breaker.is_open:
                logger.info("Primary model %s circuit OPEN, switching to fallback %s", preferred, self._fallback_model)
                return self._fallback_model
        logger.warning("All models have open circuit breakers, skipping LLM call")
        return None

    async def summarize_batch(
        self,
        articles: list[dict],
        max_tokens: int = 4096,
    ) -> list[dict]:
        if not articles:
            return []

        model = self._pick_model(self._summarize_model)
        if model is None:
            return []

        user_prompt = build_summarize_user_prompt(articles)

        response = await self._call_with_retry(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT_SUMMARIZE},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=max_tokens,
            temperature=0.1,
        )
        if response is None:
            return []

        if not response.choices:
            logger.warning("LLM returned empty choices")
            return []

        raw_text = response.choices[0].message.content or ""
        results = _parse_llm_json(raw_text)

        validated = []
        for item in results:
            if not isinstance(item, dict):
                continue
            tags = [t for t in (item.get("tags") or []) if t in VALID_TAGS]
            importance = item.get("importance", 5)
            importance = max(1, min(10, importance))

            summary = item.get("summary_ru", "")
            why = item.get("why_matters", "")
            if why and not why.startswith("-"):
                why = f"- {why}"
            full_summary = f"{summary}\n{why}".strip() if why else summary

            validated.append({
                "article_index": item.get("article_index", 0),
                "title_ru": item.get("title_ru", ""),
                "summary_ru": full_summary,
                "tags": tags,
                "importance": importance,
            })

        return validated

    async def generate_digest(
        self,
        articles: list[dict],
        system_prompt: str,
        max_tokens: int = 4096,
    ) -> str:
        if not articles:
            return ""

        model = self._pick_model(self._digest_model)
        if model is None:
            return ""

        articles_text = []
        for a in articles:
            tags_str = ", ".join(json.loads(a["tags"]) if isinstance(a["tags"], str) else a["tags"])
            articles_text.append(
                f"Title: {a['title']}\n"
                f"Summary: {a['summary_ru']}\n"
                f"Tags: {tags_str}\n"
                f"Importance: {a['importance_score']}\n"
                f"Source: {a['source_name']}\n"
                f"URL: {a['url']}\n"
            )

        user_prompt = (
            f"Create a daily AI digest from these {len(articles)} articles:\n\n"
            + "\n---\n".join(articles_text)
        )

        response = await self._call_with_retry(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=max_tokens,
            temperature=0.5,
        )
        if response is None:
            return ""

        if not response.choices:
            logger.warning("LLM returned empty choices for digest")
            return ""

        return response.choices[0].message.content or ""

    async def _call_with_retry(self, model, messages, max_tokens, temperature, retries=3):
        breaker = self._get_breaker(model)

        for attempt in range(retries):
            if breaker.is_open:
                logger.info("Circuit breaker OPEN for %s, skipping attempt %d", model, attempt + 1)
                return None

            try:
                response = await self._client.chat.completions.create(
                    model=model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                self._daily_calls += 1
                breaker.record_success()
                return response
            except Exception as e:
                error_str = str(e)
                breaker.record_failure()

                if "429" in error_str and attempt < retries - 1:
                    wait = 30 * (2 ** attempt)
                    logger.warning(
                        "Rate limited on %s, waiting %ds (attempt %d/%d, breaker: %s)",
                        model, wait, attempt + 1, retries, breaker.state.value,
                    )
                    await asyncio.sleep(wait)
                elif attempt < retries - 1 and ("timeout" in error_str.lower() or "connection" in error_str.lower()):
                    wait = 10 * (attempt + 1)
                    logger.warning("Network error on %s, retrying in %ds: %s", model, wait, e)
                    await asyncio.sleep(wait)
                else:
                    logger.error("API error on %s (breaker: %s): %s", model, breaker.state.value, e)
                    # If primary failed and circuit opened, try fallback
                    if breaker.is_open and self._fallback_model and model != self._fallback_model:
                        fb_breaker = self._get_breaker(self._fallback_model)
                        if not fb_breaker.is_open:
                            logger.info("Attempting fallback model %s", self._fallback_model)
                            return await self._call_with_retry(
                                model=self._fallback_model,
                                messages=messages,
                                max_tokens=max_tokens,
                                temperature=temperature,
                                retries=2,
                            )
                    return None
        return None

    @property
    def daily_calls(self) -> int:
        return self._daily_calls

    @property
    def circuit_breaker_stats(self) -> dict[str, dict]:
        return {model: breaker.stats for model, breaker in self._breakers.items()}

    def reset_daily_counter(self) -> None:
        self._daily_calls = 0
        for breaker in self._breakers.values():
            breaker.reset()
