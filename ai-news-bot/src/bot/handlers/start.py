from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message

from ...storage.database import Database
from ...storage import queries

router = Router()

WELCOME_TEXT = (
    "<b>AI News Digest Bot</b>\n\n"
    "Агрегирую AI-новости из 15+ источников, "
    "суммаризирую на русском и доставляю дайджест.\n\n"
    "<b>Что умею:</b>\n"
    "/digest - дайджест за сегодня\n"
    "/sources - список источников\n"
    "/tags - фильтр по темам\n"
    "/settings - настройки уведомлений\n"
    "/help - справка\n\n"
    "Ежедневный дайджест приходит в 09:00 МСК."
)


@router.message(CommandStart())
async def cmd_start(message: Message, db: Database) -> None:
    user = message.from_user
    await queries.upsert_subscriber(
        db,
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name,
    )
    await message.answer(WELCOME_TEXT, parse_mode="HTML")


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(WELCOME_TEXT, parse_mode="HTML")
