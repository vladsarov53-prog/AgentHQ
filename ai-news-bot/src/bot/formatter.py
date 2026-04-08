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
    "agentic": "\U0001f916",
    "llm_engineering": "\U0001f527",
    "models": "\U0001f9e0",
    "research": "\U0001f52c",
    "products": "\U0001f680",
    "open_source": "\U0001f4e6",
    "safety": "\U0001f6e1",
    "mcp_a2a": "\U0001f517",
    "sapr_ai": "\U0001f4d0",
    "business": "\U0001f4bc",
}

# Section display order and grouping
SECTION_ORDER = [
    ("top", "\U0001f525 ГЛАВНОЕ", 8),           # importance >= 8
    ("products", "\U0001f680 ПРОДУКТЫ И РЕЛИЗЫ", 0),
    ("models", "\U0001f9e0 МОДЕЛИ", 0),
    ("research", "\U0001f52c ИССЛЕДОВАНИЯ", 0),
    ("agentic", "\U0001f916 АГЕНТЫ И ИНСТРУМЕНТЫ", 0),
    ("open_source", "\U0001f4e6 OPEN SOURCE", 0),
    ("other", "\U0001f4cc РАЗНОЕ", 0),
]

# Tags that map to each section
SECTION_TAGS = {
    "products": {"products"},
    "models": {"models"},
    "research": {"research"},
    "agentic": {"agentic", "mcp_a2a", "llm_engineering"},
    "open_source": {"open_source"},
    "other": {"safety", "sapr_ai", "business"},
}

MONTHS_RU = {
    1: "января", 2: "февраля", 3: "марта", 4: "апреля",
    5: "мая", 6: "июня", 7: "июля", 8: "августа",
    9: "сентября", 10: "октября", 11: "ноября", 12: "декабря",
}

MAX_MESSAGE_LEN = 4000
MAX_CAPTION_LEN = 1024
MAX_DIGEST_ARTICLES = 10


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


def _get_article_section(article: dict) -> str:
    """Determine which section an article belongs to based on its tags."""
    tags = _parse_tags(article.get("tags", "[]"))
    if not tags:
        return "other"
    primary_tag = tags[0]
    for section_id, section_tags in SECTION_TAGS.items():
        if primary_tag in section_tags:
            return section_id
    return "other"


def format_digest(articles: list[dict], date_str: str) -> list[str]:
    """Format a unified digest with category grouping (like top Telegram channels)."""
    if not articles:
        return ["Новых AI-новостей пока нет. Попробуйте позже."]

    # Filter, dedup, limit
    articles = [a for a in articles if a.get("importance_score", 0) >= 5]
    articles = _dedup_articles(articles)
    articles = articles[:MAX_DIGEST_ARTICLES]

    if not articles:
        return ["\U0001f4ad Сегодня значимых новостей в AI не было."]

    date_formatted = _date_ru(date_str)

    # Split articles into sections
    top_articles = [a for a in articles if a.get("importance_score", 0) >= 8]
    regular_articles = [a for a in articles if a.get("importance_score", 0) < 8]

    # Group regular articles by section
    sections: dict[str, list[dict]] = {}
    for article in regular_articles:
        section = _get_article_section(article)
        sections.setdefault(section, []).append(article)

    # Build the digest
    lines = [f"\U0001f4e1 <b>AI-дайджест</b>  |  {escape(date_formatted)}\n"]

    article_num = 0

    # Top news first (if any)
    if top_articles:
        lines.append(f"\n\U0001f525 <b>ГЛАВНОЕ</b>\n")
        for article in top_articles:
            article_num += 1
            lines.append(_format_digest_item(article_num, article, show_why=True))
        lines.append("")

    # Regular sections
    for section_id, section_title, _ in SECTION_ORDER:
        if section_id == "top":
            continue
        section_articles = sections.get(section_id, [])
        if not section_articles:
            continue
        lines.append(f"\n{section_title}\n")
        for article in section_articles:
            article_num += 1
            lines.append(_format_digest_item(article_num, article, show_why=False))

    # Footer
    sources = set(a.get("source_name", "") for a in articles)
    lines.append(f"\n\U0001f4ca {article_num} новостей из {len(sources)} источников")

    text = "\n".join(lines)

    if len(text) <= MAX_MESSAGE_LEN:
        return [text]

    return _split_messages(lines)


def _format_digest_item(num: int, article: dict, show_why: bool = False) -> str:
    """Format a single article in the unified digest."""
    title = escape(_get_title_ru(article))
    url = article.get("url", "")
    source = escape(article.get("source_name", ""))

    tags = _parse_tags(article.get("tags", "[]"))
    emoji = TAG_EMOJI.get(tags[0], "\U0001f4cc") if tags else "\U0001f4cc"

    # Summary
    summary = article.get("summary_ru", "")
    summary_lines = summary.split("\n")
    main_summary = summary_lines[0] if summary_lines else ""
    why_matters = ""
    if len(summary_lines) > 1:
        why_matters = summary_lines[1].strip()

    if len(main_summary) > 200:
        main_summary = main_summary[:197] + "..."
    main_summary = escape(main_summary)

    parts = [f"{emoji} <b>{num}. {title}</b>"]
    parts.append(main_summary)

    if show_why and why_matters:
        why_clean = why_matters.lstrip("- ").strip()
        if why_clean:
            parts.append(f"<i>Почему важно: {escape(why_clean)}</i>")

    parts.append(f"\U0001f517 <a href=\"{escape(url)}\">Читать оригинал</a>  |  {source}")

    return "\n".join(parts)


def format_digest_cards(articles: list[dict], date_str: str) -> list[DigestCard]:
    """Format digest as a single unified message (not separate cards)."""
    messages = format_digest(articles, date_str)
    return [DigestCard(text=msg) for msg in messages]


def format_instant(article: dict) -> str:
    title = escape(_get_title_ru(article))
    url = escape(article.get("url", ""))
    source = escape(article.get("source_name", ""))

    tags = _parse_tags(article.get("tags", "[]"))
    emoji = TAG_EMOJI.get(tags[0], "\U0001f525") if tags else "\U0001f525"

    # Summary with why_matters
    summary = article.get("summary_ru", "")
    summary_lines = summary.split("\n")
    main_summary = escape(summary_lines[0]) if summary_lines else ""

    why_matters = ""
    if len(summary_lines) > 1:
        why_clean = summary_lines[1].strip().lstrip("- ").strip()
        if why_clean:
            why_matters = f"\n<i>Почему важно: {escape(why_clean)}</i>"

    return (
        f"{emoji} <b>{title}</b>\n\n"
        f"{main_summary}"
        f"{why_matters}\n\n"
        f"\U0001f517 <a href=\"{url}\">Читать оригинал</a>  |  {source}"
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
