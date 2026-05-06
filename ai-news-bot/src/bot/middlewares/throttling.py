from __future__ import annotations

import time
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message


class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, rate_limit: float = 1.0):
        self._rate_limit = rate_limit
        self._users: dict[int, float] = {}
        self._last_cleanup = time.monotonic()

    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        user_id = event.from_user.id if event.from_user else 0
        now = time.monotonic()

        # Cleanup stale entries every hour to prevent unbounded growth
        if now - self._last_cleanup > 3600:
            cutoff = now - 86400
            self._users = {uid: t for uid, t in self._users.items() if t > cutoff}
            self._last_cleanup = now

        last_time = self._users.get(user_id, 0)
        if now - last_time < self._rate_limit:
            return None

        self._users[user_id] = now
        return await handler(event, data)
