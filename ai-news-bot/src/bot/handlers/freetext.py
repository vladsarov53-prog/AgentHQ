from __future__ import annotations

import re

from aiogram import Router
from aiogram.types import Message

from ...storage.database import Database
from .digest import cmd_digest
from .sources import cmd_sources
from .admin import cmd_force_fetch, cmd_stats

router = Router()

PATTERNS = {
    "digest": [
        r"дайджест", r"новост", r"что нового", r"сводк", r"обзор",
        r"покажи", r"расскажи", r"что там", r"что происходит",
        r"что интересного", r"свежее", r"свежие", r"последн",
        r"что случилось", r"апдейт", r"update", r"news",
        r"что в мире ?(ai|ии)", r"digest",
    ],
    "force_fetch": [
        r"собери", r"обнови", r"загрузи", r"fetch", r"запусти сбор",
        r"обновить", r"загрузить",
    ],
    "sources": [
        r"источник", r"откуда", r"каналы", r"подписк", r"sources",
    ],
    "stats": [
        r"статистик", r"сколько", r"stats", r"цифры",
    ],
    "help": [
        r"помощь", r"помоги", r"что умеешь", r"команд", r"как пользоват",
        r"help", r"старт", r"привет", r"здравствуй",
    ],
}


def _match(text: str) -> str | None:
    text = text.lower().strip()
    for action, patterns in PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text):
                return action
    return None


@router.message()
async def handle_freetext(message: Message, db: Database, admin_id: int = 0, pipeline=None) -> None:
    text = message.text or ""
    action = _match(text)

    if action == "digest":
        await cmd_digest(message, db, pipeline)
    elif action == "force_fetch":
        await cmd_force_fetch(message, db, admin_id, pipeline)
    elif action == "sources":
        await cmd_sources(message, db)
    elif action == "stats":
        await cmd_stats(message, db, admin_id)
    elif action == "help":
        from .start import WELCOME_TEXT
        await message.answer(WELCOME_TEXT, parse_mode="HTML")
    else:
        await message.answer(
            "Не понял. Попробуйте:\n"
            "- \"Покажи новости\" - дайджест\n"
            "- \"Обнови\" - собрать свежие\n"
            "- \"Источники\" - список\n"
            "- \"Статистика\" - цифры\n"
            "- /help - все команды"
        )
