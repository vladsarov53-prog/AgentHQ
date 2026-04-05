from __future__ import annotations

import json
from html import escape

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


def _date_ru(date_str: str) -> str:
    """Convert date to Russian format."""
    from datetime import datetime
    try:
        dt = datetime.strptime(date_str, "%d %B %Y")
        return f"{dt.day} {MONTHS_RU[dt.month]} {dt.year}"
    except Exception:
        return date_str


def format_digest(articles: list[dict], date_str: str) -> list[str]:
    if not articles:
        return ["Новых AI-новостей пока нет. Попробуйте позже."]

    # Filter out noise (importance < 4)
    articles = [a for a in articles if a.get("importance_score", 0) >= 4]

    if not articles:
        return ["Сегодня значимых новостей в AI не было."]

    date_formatted = _date_ru(date_str)
    messages = []
    current = f"📡 <b>AI-дайджест</b>  |  {escape(date_formatted)}\n"

    # Split by importance
    important = [a for a in articles if a.get("importance_score", 0) >= 8]
    regular = [a for a in articles if 4 <= a.get("importance_score", 0) < 8]

    # IMPORTANT section
    if important:
        current += "\n🔥 <b>Главное</b>\n"
        for article in important:
            current += "\n" + _format_card(article) + "\n"

    # Regular grouped by tag
    tag_groups: dict[str, list[dict]] = {}
    for article in regular:
        tags = _parse_tags(article.get("tags", "[]"))
        first_tag = tags[0] if tags else "other"
        tag_groups.setdefault(first_tag, []).append(article)

    sorted_groups = sorted(
        tag_groups.items(),
        key=lambda x: sum(a.get("importance_score", 0) for a in x[1]),
        reverse=True,
    )

    for tag_id, group in sorted_groups:
        emoji = TAG_EMOJI.get(tag_id, "📌")
        label = TAG_LABELS.get(tag_id, "Разное")
        section = f"\n{emoji} <b>{escape(label)}</b>\n"
        for article in group:
            section += "\n" + _format_card(article) + "\n"

        if len(current) + len(section) > MAX_MESSAGE_LEN:
            messages.append(current)
            current = section
        else:
            current += section

    total = len(important) + len(regular)
    sources = set(a.get("source_name", "") for a in articles)
    footer = f"\n{'~' * 28}\n📊 {total} новостей  |  {len(sources)} источников"

    if len(current) + len(footer) > MAX_MESSAGE_LEN:
        messages.append(current)
        messages.append(footer)
    else:
        current += footer
        messages.append(current)

    return messages


def format_instant(article: dict) -> str:
    title = escape(_get_title_ru(article))
    summary = escape(article.get("summary_ru", ""))
    source = escape(article.get("source_name", ""))
    url = escape(article.get("url", ""))
    tags = _parse_tags(article.get("tags", "[]"))
    tag_line = " ".join(TAG_EMOJI.get(t, "") for t in tags)

    return (
        f"🔥 <b>{title}</b>\n\n"
        f"{summary}\n\n"
        f"{tag_line}  {source}\n"
        f"<a href=\"{url}\">Читать</a>"
    )


def _format_card(article: dict) -> str:
    title = escape(_get_title_ru(article))
    summary = escape(article.get("summary_ru", ""))
    url = escape(article.get("url", ""))
    source = escape(article.get("source_name", ""))

    return (
        f"<b>{title}</b>\n"
        f"{summary}\n"
        f"<a href=\"{url}\">~ {source}</a>"
    )


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
