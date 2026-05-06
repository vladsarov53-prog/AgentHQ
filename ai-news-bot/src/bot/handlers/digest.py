from __future__ import annotations

import logging
from datetime import datetime

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from ...storage.database import Database
from ...storage import queries
from ..formatter import format_digest_cards

router = Router()
logger = logging.getLogger(__name__)


@router.message(Command("digest"))
async def cmd_digest(message: Message, db: Database, pipeline=None) -> None:
    articles = await queries.get_digest_articles(db, hours=24, limit=20)

    # If no articles and pipeline available, auto-fetch first
    if not articles and pipeline:
        await message.answer("Собираю свежие новости, подождите...")
        try:
            stats = await pipeline.run_fetch_cycle()
            logger.info("Auto-fetch for digest: %s", stats)
            articles = await queries.get_digest_articles(db, hours=24, limit=20)
        except Exception as e:
            logger.error("Auto-fetch failed: %s", e)

    if not articles:
        await message.answer(
            "Свежих новостей пока нет. Источники проверены, но ничего нового за последние 24 часа."
        )
        return

    date_str = datetime.now().strftime("%d %B %Y")
    cards = format_digest_cards(articles, date_str)

    for card in cards:
        if card.image_url:
            try:
                await message.answer_photo(
                    photo=card.image_url,
                    caption=card.text,
                    parse_mode="HTML",
                )
                continue
            except Exception as e:
                logger.debug("send_photo failed, falling back to text: %s", e)

        await message.answer(
            card.text,
            parse_mode="HTML",
            disable_web_page_preview=False,
        )
