"""Track in-flight Telegram handlers and log update dispatch."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from aiogram.dispatcher.middlewares.base import BaseMiddleware
from aiogram.types import TelegramObject, User

logger = logging.getLogger(__name__)


class AdmissionTurn:
    """Release one user's ordered update turn after queue admission."""

    def __init__(self, release: Callable[[], None]) -> None:
        self._release = release
        self._released = False

    def release(self) -> None:
        """Release the turn once; middleware cleanup may safely call this again."""
        if self._released:
            return
        self._released = True
        self._release()


@dataclass(slots=True)
class _AdmissionLane:
    lock: asyncio.Lock
    references: int = 0


class OrderedAdmissionMiddleware(BaseMiddleware):
    """Keep each user's updates ordered until its handler admits or rejects work."""

    def __init__(self) -> None:
        self._lanes: dict[int, _AdmissionLane] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if not isinstance(user, User):
            return await handler(event, data)

        lane = self._lanes.get(user.id)
        if lane is None:
            lane = _AdmissionLane(asyncio.Lock())
            self._lanes[user.id] = lane
        lane.references += 1
        try:
            await lane.lock.acquire()
        except BaseException:
            self._drop_reference(user.id, lane)
            raise

        turn = AdmissionTurn(lambda: self._release(user.id, lane))
        data["admission_turn"] = turn
        try:
            return await handler(event, data)
        finally:
            turn.release()

    def _release(self, user_id: int, lane: _AdmissionLane) -> None:
        lane.lock.release()
        self._drop_reference(user_id, lane)

    def _drop_reference(self, user_id: int, lane: _AdmissionLane) -> None:
        lane.references -= 1
        if lane.references == 0 and self._lanes.get(user_id) is lane:
            del self._lanes[user_id]


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

    async def stop_accepting(self) -> None:
        """Reject handlers that have not entered while preserving active calls."""
        async with self._condition:
            self._accepting = False

    async def wait_until_idle(self) -> None:
        """Wait until every previously admitted handler has returned."""
        async with self._condition:
            await self._condition.wait_for(lambda: self._active == 0)

    async def stop_and_wait(self) -> None:
        """Backward-compatible composition of the two shutdown phases."""
        await self.stop_accepting()
        await self.wait_until_idle()


def _handler_name(
    handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
) -> str:
    return getattr(handler, "__name__", handler.__class__.__name__)


class UpdateLoggingMiddleware(BaseMiddleware):
    """Log every incoming update as compact JSON without null-valued fields."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        logger.debug(
            "incoming_update payload=%s",
            event.model_dump_json(by_alias=True, exclude_none=True),
        )
        return await handler(event, data)


class HandlerLoggingMiddleware(BaseMiddleware):
    """Log the concrete handler selected after aiogram filters pass."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        handler_object = data.get("handler")
        callback = getattr(handler_object, "callback", handler)
        update_id = getattr(data.get("event_update"), "update_id", None)
        try:
            return await handler(event, data)
        finally:
            logger.debug(
                "update_processed update_id=%s handler=%s",
                update_id,
                _handler_name(callback),
            )


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
