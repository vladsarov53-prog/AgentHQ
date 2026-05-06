from __future__ import annotations

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery

from ...storage.database import Database
from ...storage import queries
from ..keyboards import settings_keyboard, tags_keyboard

router = Router()


@router.message(Command("settings"))
async def cmd_settings(message: Message, db: Database) -> None:
    sub = await _get_subscriber(db, message.from_user.id)
    if not sub:
        await message.answer("Сначала подпишитесь: /start")
        return

    await message.answer(
        "<b>Настройки уведомлений:</b>",
        parse_mode="HTML",
        reply_markup=settings_keyboard(
            instant_enabled=bool(sub["instant_enabled"]),
            digest_enabled=bool(sub["digest_enabled"]),
        ),
    )


@router.callback_query(F.data.startswith("set:"))
async def on_setting_toggle(callback: CallbackQuery, db: Database) -> None:
    action = callback.data.split(":", 1)[1]
    user_id = callback.from_user.id
    sub = await _get_subscriber(db, user_id)

    if not sub:
        await callback.answer("Подпишитесь через /start")
        return

    if action == "instant":
        new_val = not bool(sub["instant_enabled"])
        await queries.update_subscriber_settings(db, user_id, instant_enabled=new_val)
        sub["instant_enabled"] = int(new_val)
    elif action == "digest":
        new_val = not bool(sub["digest_enabled"])
        await queries.update_subscriber_settings(db, user_id, digest_enabled=new_val)
        sub["digest_enabled"] = int(new_val)
    elif action == "tags":
        import json
        selected = []
        if sub.get("tag_filter"):
            try:
                selected = json.loads(sub["tag_filter"])
            except (json.JSONDecodeError, TypeError):
                pass
        await callback.message.edit_text(
            "Выберите темы:",
            reply_markup=tags_keyboard(selected),
        )
        await callback.answer()
        return

    await callback.message.edit_reply_markup(
        reply_markup=settings_keyboard(
            instant_enabled=bool(sub["instant_enabled"]),
            digest_enabled=bool(sub["digest_enabled"]),
        ),
    )
    await callback.answer("Сохранено")


async def _get_subscriber(db: Database, telegram_id: int) -> dict | None:
    cursor = await db.conn.execute(
        "SELECT * FROM subscribers WHERE telegram_id = ?", (telegram_id,)
    )
    row = await cursor.fetchone()
    return dict(row) if row else None
