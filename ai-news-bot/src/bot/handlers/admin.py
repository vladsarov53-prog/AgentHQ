from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from ...storage.database import Database
from ...storage import queries

logger = logging.getLogger(__name__)

router = Router()


@router.message(Command("stats"))
async def cmd_stats(message: Message, db: Database, admin_id: int) -> None:
    if message.from_user.id != admin_id:
        await message.answer("Доступ только для администратора.")
        return

    stats = await queries.get_stats(db)

    text = (
        "<b>Статистика бота:</b>\n\n"
        f"Статей всего: {stats['total_articles']}\n"
        f"Обработано: {stats['processed_articles']}\n"
        f"Подписчиков: {stats['active_subscribers']}\n"
        f"Источников: {stats['active_sources']}\n"
        f"С ошибками: {stats['sources_with_errors']}"
    )
    await message.answer(text, parse_mode="HTML")


@router.message(Command("force_fetch"))
async def cmd_force_fetch(message: Message, db: Database, admin_id: int, pipeline=None) -> None:
    if message.from_user.id != admin_id:
        await message.answer("Доступ только для администратора.")
        return

    if pipeline is None:
        await message.answer("Pipeline не инициализирован.")
        return

    await message.answer("Запускаю принудительный цикл сбора...")

    try:
        result = await pipeline.run_fetch_cycle()
        text = (
            f"Цикл завершен:\n"
            f"Собрано: {result['fetched']}\n"
            f"Новых: {result['new']}\n"
            f"Дубликатов: {result['duplicates']}\n"
            f"Обработано LLM: {result['processed']}\n"
            f"Ошибок: {result['errors']}"
        )
    except Exception as e:
        logger.error("Force fetch error: %s", e)
        text = f"Ошибка: {e}"

    await message.answer(text)


@router.message(Command("health"))
async def cmd_health(message: Message, db: Database, admin_id: int) -> None:
    if message.from_user.id != admin_id:
        await message.answer("Доступ только для администратора.")
        return

    health = await queries.get_health_status(db)

    status = "OK" if (health["stuck_articles"] == 0 and health["stale_sources"] == 0) else "ISSUES"
    text = (
        f"<b>Health Check: {status}</b>\n\n"
        f"Необработанных: {health['unprocessed']}\n"
        f"Зависших (>6ч): {health['stuck_articles']}\n"
        f"Источников без фетча: {health['stale_sources']}\n"
        f"Источников с ошибками: {health['error_sources']}\n"
        f"Обработано за 24ч: {health['processed_24h']}\n"
        f"LLM-failed: {health['llm_failed']}\n"
        f"Последний фетч: {health['last_fetch'] or 'никогда'}"
    )
    await message.answer(text, parse_mode="HTML")
