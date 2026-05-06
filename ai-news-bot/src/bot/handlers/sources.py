from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from html import escape

from ...storage.database import Database
from ...storage import queries

router = Router()


@router.message(Command("sources"))
async def cmd_sources(message: Message, db: Database) -> None:
    sources = await queries.get_active_sources(db)

    if not sources:
        await message.answer("Источники пока не настроены.")
        return

    by_category: dict[str, list] = {}
    for s in sources:
        cat = s.get("category", "other")
        by_category.setdefault(cat, []).append(s)

    lines = ["<b>Активные источники:</b>\n"]
    for category, source_list in by_category.items():
        lines.append(f"\n<b>{escape(category.upper())}</b>")
        for s in source_list:
            status = "[ok]" if s["error_count"] == 0 else f"[err:{s['error_count']}]"
            lines.append(f"  {status} {escape(s['name'])}")

    inactive_count = len([s for s in sources if not s.get("is_active", True)])
    lines.append(f"\nВсего: {len(sources)} активных")
    if inactive_count:
        lines.append(f"Отключено: {inactive_count}")

    await message.answer("\n".join(lines), parse_mode="HTML")
