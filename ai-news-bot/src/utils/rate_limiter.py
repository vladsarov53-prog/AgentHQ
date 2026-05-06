from __future__ import annotations

import asyncio
import time


class RateLimiter:
    def __init__(self, max_calls: int, period: float = 60.0):
        self._max_calls = max_calls
        self._period = period
        self._calls: list[float] = []
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            self._calls = [t for t in self._calls if now - t < self._period]

            if len(self._calls) >= self._max_calls:
                wait = self._period - (now - self._calls[0])
                if wait > 0:
                    await asyncio.sleep(wait)

            self._calls.append(time.monotonic())

    @property
    def remaining(self) -> int:
        now = time.monotonic()
        active = [t for t in self._calls if now - t < self._period]
        return max(0, self._max_calls - len(active))
