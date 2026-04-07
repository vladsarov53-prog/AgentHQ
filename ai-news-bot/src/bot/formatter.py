from __future__ import annotations

import json
from dataclasses import dataclass
from html import escape

from ..processing.dedup import titles_are_similar


@dataclass
class DigestCard:
    """A single digest item: text + optional image."""
    text: str
    image_url: str | None = None


TAG_LABELS = {
    "agentic": "Агентные системы",
    "llm_engineering": "LLM-инженерия",
    "models": "Модели",
    "research": "Исследования",
    "products": "Продукты",
    "open_source": "Open Source",
    "safety": "Безопасность AI",
    "mcp_a2a": "MCP / A2A",
    "sapr_ai": "САПР + AI",
    "business": "AI в бизнесе",
}

TAG_EMOJI = {
    "agentic": "🤖",
    "llm_engineering": "🔧",
    "models": "🧠",
    "research": "🔬",
    "products": "🚀",
    "open_source": "📦",
    "safety": "🛡",
    "mcp_a2a": "🔗",
    "sapr_ai": "📐",
    "business": "💼",
}

MONTHS_RU = {
    1: "января", 2: "февраля", 3: "марта", 4: "апреля",
    5: "мая", 6: "июня", 7: "июля", 8: "августа",
    9: "сентября", 10: "октября", 11: "ноября", 12: "декабря",
}

MAX_MESSAGE_LEN = 4000
MAX_CAPTION_LEN = 1024  # Telegram photo caption limit
MAX_DIGEST_ARTICLES = 5


def _date_ru(date_str: str) -> str:
    from datetime import datetime
    try:
        dt = datetime.strptime(date_str, "%d %B %Y")
        return f"{dt.day} {MONTHS_RU[dt.month]} {dt.year}"
    except Exception:
        return date_str


def _dedup_articles(articles: list[dict]) -> list[dict]:
    """Remove semantically similar articles, keeping the one with higher importance."""
    result: list[dict] = []
    for article in articles:
        title = article.get("title_ru") or article.get("title", "")
        is_dup = False
        for kept in result:
            kept_title = kept.get("title_ru") or kept.get("title", "")
            if titles_are_similar(title, kept_title):
                is_dup = True
                break
        if not is_dup:
            result.append(article)
    return result


def format_digest(articles: list[dict], date_str: str) -> list[str]:
    if not articles:
        return ["Новых AI-новостей пока нет. Попробуйте позже."]

    # Only significant news (importance >= 6), top 5
    articles = [a for a in articles if a.get("importance_score", 0) >= 6]
    articles = _dedup_articles(articles)
    articles = articles[:MAX_DIGEST_ARTICLES]

    if not articles:
        return ["Сегодня значимых новостей в AI не было."]

    date_formatted = _date_ru(date_str)

    # Header
    lines = [f"📡 <b>AI-дайджест</b>  |  {escape(date_formatted)}\n"]

    # Numbered compact cards
    for i, article in enumerate(articles, 1):
        lines.append(_format_compact_card(i, article))

    # Footer
    sources = set(a.get("source_name", "") for a in articles)
    lines.append(f"\n{len(articles)} новостей из {len(sources)} источников")

    text = "\n".join(lines)

    # Split if too long
    if len(text) <= MAX_MESSAGE_LEN:
        return [text]

    return _split_messages(lines)


def _format_compact_card(num: int, article: dict) -> str:
    """Compact card: number, emoji, title as link, one-line summary."""
    title = escape(_get_title_ru(article))
    url = escape(article.get("url", ""))
    source = escape(article.get("source_name", ""))

    tags = _parse_tags(article.get("tags", "[]"))
    emoji = TAG_EMOJI.get(tags[0], "📌") if tags else "📌"

    # Summary: first sentence only, trim to 120 chars
    summary = article.get("summary_ru", "")
    if "\n" in summary:
        summary = summary.split("\n")[0]
    if len(summary) > 140:
        summary = summary[:137] + "..."
    summary = escape(summary)

    return (
        f"\n{emoji} <b>{num}. <a href=\"{url}\">{title}</a></b>\n"
        f"{summary}\n"
        f"<i>{source}</i>"
    )


def format_digest_cards(articles: list[dict], date_str: str) -> list[DigestCard]:
    """Format digest as individual cards with images for rich Telegram display."""
    if not articles:
        return [DigestCard(text="Новых AI-новостей пока нет. Попробуйте позже.")]

    articles = [a for a in articles if a.get("importance_score", 0) >= 6]
    articles = _dedup_articles(articles)
    articles = articles[:MAX_DIGEST_ARTICLES]

    if not articles:
        return [DigestCard(text="Сегодня значимых новостей в AI не было.")]

    date_formatted = _date_ru(date_str)
    cards: list[DigestCard] = []

    # Header card (no image)
    cards.append(DigestCard(
        text=f"📡 <b>AI-дайджест</b>  |  {escape(date_formatted)}"
    ))

    # Individual article cards
    for i, article in enumerate(articles, 1):
        caption = _format_photo_caption(i, article)
        image = article.get("image_url") or None
        cards.append(DigestCard(text=caption, image_url=image))

    # Footer
    sources = set(a.get("source_name", "") for a in articles)
    cards.append(DigestCard(
        text=f"{len(articles)} новостей из {len(sources)} источников"
    ))

    return cards


def _format_photo_caption(num: int, article: dict) -> str:
    """Format article as a photo caption (max 1024 chars for Telegram)."""
    title = escape(_get_title_ru(article))
    url = article.get("url", "")
    source = escape(article.get("source_name", ""))

    tags = _parse_tags(article.get("tags", "[]"))
    emoji = TAG_EMOJI.get(tags[0], "📌") if tags else "📌"

    # Tag label
    tag_label = ""
    if tags:
        label = TAG_LABELS.get(tags[0], "")
        if label:
            tag_label = f"  #{escape(label)}"

    # Summary: trim to fit caption limit
    summary = article.get("summary_ru") or ""
    if "\n" in summary:
        summary = summary.split("\n")[0]
    if len(summary) > 200:
        summary = summary[:197] + "..."
    summary = escape(summary)

    caption = (
        f"{emoji} <b>{num}. {title}</b>{tag_label}\n\n"
        f"{summary}\n\n"
        f"<a href=\"{escape(url)}\">Читать</a>  |  <i>{source}</i>"
    )

    # Ensure it fits the caption limit
    if len(caption) > MAX_CAPTION_LEN:
        # Shorten summary to fit
        over = len(caption) - MAX_CAPTION_LEN + 10
        summary = summary[:len(summary) - over] + "..."
        caption = (
            f"{emoji} <b>{num}. {title}</b>{tag_label}\n\n"
            f"{summary}\n\n"
            f"<a href=\"{escape(url)}\">Читать</a>  |  <i>{source}</i>"
        )

    return caption


def format_instant(article: dict) -> str:
    title = escape(_get_title_ru(article))
    url = escape(article.get("url", ""))
    source = escape(article.get("source_name", ""))

    tags = _parse_tags(article.get("tags", "[]"))
    emoji = TAG_EMOJI.get(tags[0], "🔥") if tags else "🔥"

    # Summary: first sentence only
    summary = article.get("summary_ru", "")
    if "\n" in summary:
        summary = summary.split("\n")[0]
    summary = escape(summary)

    return (
        f"{emoji} <b>{title}</b>\n\n"
        f"{summary}\n\n"
        f"<a href=\"{url}\">{source}</a>"
    )


def _split_messages(lines: list[str]) -> list[str]:
    messages = []
    current = ""
    for line in lines:
        if len(current) + len(line) + 1 > MAX_MESSAGE_LEN:
            if current:
                messages.append(current)
            current = line
        else:
            current = current + "\n" + line if current else line
    if current:
        messages.append(current)
    return messages


def _get_title_ru(article: dict) -> str:
    title_ru = article.get("title_ru") or ""
    if title_ru and len(title_ru) > 3:
        return title_ru
    return article.get("title", "")


def _parse_tags(tags) -> list[str]:
    if isinstance(tags, list):
        return tags
    if isinstance(tags, str):
        try:
            return json.loads(tags)
        except (json.JSONDecodeError, TypeError):
            return []
    return []
