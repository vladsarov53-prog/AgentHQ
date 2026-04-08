from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties

from .config.settings import EnvSettings, load_yaml_config
from .storage.database import Database
from .storage.queries import sync_sources
from .processing.llm import LLMProcessor
from .processing.pipeline import Pipeline
from .bot.app import create_dispatcher
from .bot.scheduler import setup_scheduler

# Data directory: use DATA_DIR env var (for Railway volume) or default to ./data
DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).parent.parent / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

# In containers (Railway), stdout is captured automatically - no file logging needed
_handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
if not os.environ.get("DATA_DIR"):
    # Local dev: also log to file
    (DATA_DIR / "logs").mkdir(parents=True, exist_ok=True)
    _handlers.append(logging.FileHandler(
        DATA_DIR / "logs" / "bot.log", encoding="utf-8",
    ))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=_handlers,
)
# Suppress noisy httpx request logs (every GET/POST logged at INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

_shutdown_event: asyncio.Event | None = None


async def main() -> None:
    global _shutdown_event
    _shutdown_event = asyncio.Event()

    # Load config
    env = EnvSettings()
    config = load_yaml_config()
    logger.info("Config loaded: %d sources, %d tags", len(config.sources), len(config.tags))

    # Validate config at startup
    _validate_config(config)

    # Initialize database
    db_path = DATA_DIR / "news.db"
    db = await Database.create(db_path)
    await sync_sources(db, config.sources)
    logger.info("Database ready")

    # Initialize LLM
    llm = LLMProcessor(
        api_key=env.openrouter_api_key,
        summarize_model=config.llm.summarize_model,
        digest_model=config.llm.digest_model,
        fallback_model=config.llm.fallback_model,
    )

    # Initialize pipeline
    pipeline = Pipeline(db=db, llm=llm, config=config)

    # Create bot
    bot = Bot(
        token=env.telegram_bot_token,
        default=DefaultBotProperties(parse_mode="HTML"),
    )

    # Create dispatcher with dependency injection
    dp = create_dispatcher()

    # Start scheduler
    scheduler = setup_scheduler(
        db=db, bot=bot, pipeline=pipeline, llm=llm, config=config,
        admin_id=env.admin_telegram_id,
    )
    scheduler.start()
    logger.info("Scheduler started")

    # Setup graceful shutdown
    def _signal_handler(*_):
        logger.info("Shutdown signal received")
        if _shutdown_event:
            _shutdown_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            asyncio.get_running_loop().add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            signal.signal(sig, _signal_handler)

    # Drop pending updates and webhook before polling (critical for clean start)
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Webhook cleared, pending updates dropped")

    # Start polling
    try:
        logger.info("Bot starting polling...")
        await dp.start_polling(
            bot,
            db=db,
            admin_id=env.admin_telegram_id,
            pipeline=pipeline,
        )
    finally:
        scheduler.shutdown(wait=True)
        await pipeline.close()
        await db.close()
        await bot.session.close()
        logger.info("Bot stopped")


def _validate_config(config) -> None:
    from urllib.parse import urlparse
    errors = []
    for source in config.sources:
        parsed = urlparse(source.url)
        if parsed.scheme not in ("http", "https"):
            errors.append(f"Invalid URL scheme '{parsed.scheme}' for source '{source.name}'")
        if not parsed.netloc:
            errors.append(f"No host in URL for source '{source.name}'")

    if errors:
        for err in errors:
            logger.error("Config validation: %s", err)
        raise ValueError(f"Config validation failed: {len(errors)} errors")

    logger.info("Config validation passed")


def run() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    run()
