from __future__ import annotations

import json

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery

from ...storage.database import Database
from ...storage import queries
from ..keyboards import tags_keyboard

router = Router()


@router.message(Command("tags"))
async def cmd_tags(message: Message, db: Database) -> None:
    sub = await _get_subscriber(db, message.from_user.id)
    selected = _parse_filter(sub.get("tag_filter") if sub else None)

    await message.answer(
        "Выберите темы для получения новостей.\nОтмеченные темы включены в ваш фильтр:",
        reply_markup=tags_keyboard(selected),
    )


@router.callback_query(F.data.startswith("tag:"))
async def on_tag_toggle(callback: CallbackQuery, db: Database) -> None:
    action = callback.data.split(":", 1)[1]
    user_id = callback.from_user.id

    sub = await _get_subscriber(db, user_id)
    selected = _parse_filter(sub.get("tag_filter") if sub else None)

    if action == "all":
        selected = []
    elif action == "done":
        filter_value = selected if selected else None
        await queries.update_subscriber_settings(
            db, user_id, tag_filter=filter_value,
        )
        text = "Все темы" if not selected else ", ".join(selected)
        await callback.message.edit_text(f"Фильтр сохранен: {text}")
        await callback.answer()
        return
    else:
        if action in selected:
            selected.remove(action)
        else:
            selected.append(action)

    await callback.message.edit_reply_markup(reply_markup=tags_keyboard(selected))
    await callback.answer()


async def _get_subscriber(db: Database, telegram_id: int) -> dict | None:
    cursor = await db.conn.execute(
        "SELECT * FROM subscribers WHERE telegram_id = ?", (telegram_id,)
    )
    row = await cursor.fetchone()
    return dict(row) if row else None


def _parse_filter(tag_filter) -> list[str]:
    if not tag_filter:
        return []
    if isinstance(tag_filter, list):
        return tag_filter
    try:
        return json.loads(tag_filter)
    except (json.JSONDecodeError, TypeError):
        return []
