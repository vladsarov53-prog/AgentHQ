from __future__ import annotations

import asyncio
import json
import logging
import re

from openai import AsyncOpenAI

from .prompts import SYSTEM_PROMPT_SUMMARIZE, build_summarize_user_prompt
from .sanitizer import sanitize_llm_output

logger = logging.getLogger(__name__)

VALID_TAGS = {
    "agentic", "llm_engineering", "models", "research", "products",
    "open_source", "safety", "mcp_a2a", "sapr_ai", "business",
}


class LLMProcessor:
    def __init__(self, api_key: str, summarize_model: str, digest_model: str):
        self._client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )
        self._summarize_model = summarize_model
        self._digest_model = digest_model
        self._daily_calls = 0

    async def summarize_batch(
        self,
        articles: list[dict],
        max_tokens: int = 4096,
    ) -> list[dict]:
        if not articles:
            return []

        user_prompt = build_summarize_user_prompt(articles)

        response = await self._call_with_retry(
            model=self._summarize_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT_SUMMARIZE},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=max_tokens,
            temperature=0.3,
        )
        if response is None:
            return []

        raw_text = response.choices[0].message.content or ""
        cleaned = sanitize_llm_output(raw_text)

        # Extract JSON array from response
        match = re.search(r'\[.*\]', cleaned, re.DOTALL)
        if match:
            cleaned = match.group(0)

        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            logger.error("Failed to parse JSON (len=%d): %.300s", len(cleaned), cleaned)
            return []

        if isinstance(parsed, dict):
            results = parsed.get("articles", parsed.get("results", [parsed]))
        elif isinstance(parsed, list):
            results = parsed
        else:
            return []

        validated = []
        for item in results:
            tags = [t for t in item.get("tags", []) if t in VALID_TAGS]
            importance = item.get("importance", 5)
            importance = max(1, min(10, importance))

            # Combine summary + why_matters into one field for storage
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
            model=self._digest_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=max_tokens,
            temperature=0.5,
        )
        if response is None:
            return ""

        return response.choices[0].message.content or ""

    async def _call_with_retry(self, model, messages, max_tokens, temperature, retries=3):
        for attempt in range(retries):
            try:
                response = await self._client.chat.completions.create(
                    model=model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                self._daily_calls += 1
                return response
            except Exception as e:
                if "429" in str(e) and attempt < retries - 1:
                    wait = 20 * (attempt + 1)
                    logger.warning("Rate limited, waiting %ds (attempt %d/%d)", wait, attempt + 1, retries)
                    await asyncio.sleep(wait)
                else:
                    logger.error("API error: %s", e)
                    return None
        return None

    @property
    def daily_calls(self) -> int:
        return self._daily_calls

    def reset_daily_counter(self) -> None:
        self._daily_calls = 0
