from __future__ import annotations

from aiogram import Dispatcher

from .handlers import start, digest, sources, tags, settings, admin, freetext
from .middlewares.throttling import ThrottlingMiddleware


def create_dispatcher() -> Dispatcher:
    dp = Dispatcher()

    dp.message.middleware(ThrottlingMiddleware(rate_limit=0.5))

    dp.include_router(start.router)
    dp.include_router(digest.router)
    dp.include_router(sources.router)
    dp.include_router(tags.router)
    dp.include_router(settings.router)
    dp.include_router(admin.router)
    dp.include_router(freetext.router)  # последний - ловит всё остальное

    return dp
