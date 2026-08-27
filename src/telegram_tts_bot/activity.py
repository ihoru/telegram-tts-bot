"""Track in-flight Telegram handlers for graceful shutdown."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram.dispatcher.middlewares.base import BaseMiddleware
from aiogram.types import TelegramObject


class HandlerActivity:
    """Allow shutdown to stop intake and wait for active handler calls."""

    def __init__(self) -> None:
        self._accepting = True
        self._active = 0
        self._condition = asyncio.Condition()

    async def enter(self) -> bool:
        async with self._condition:
            if not self._accepting:
                return False
            self._active += 1
            return True

    async def leave(self) -> None:
        async with self._condition:
            if self._active <= 0:
                raise RuntimeError("handler activity released more than once")
            self._active -= 1
            if self._active == 0:
                self._condition.notify_all()

    async def stop_and_wait(self) -> None:
        async with self._condition:
            self._accepting = False
            await self._condition.wait_for(lambda: self._active == 0)


class HandlerActivityMiddleware(BaseMiddleware):
    """Apply ``HandlerActivity`` to every update dispatched by aiogram."""

    def __init__(self, activity: HandlerActivity) -> None:
        self._activity = activity

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not await self._activity.enter():
            return None
        try:
            return await handler(event, data)
        finally:
            await self._activity.leave()
