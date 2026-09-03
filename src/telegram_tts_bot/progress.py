"""Aggregated Telegram queue notices and active-render chat actions."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from aiogram import Bot
from aiogram.enums import ChatAction
from aiogram.exceptions import TelegramRetryAfter
from aiogram.types import ReplyParameters

Sleep = Callable[[float], Awaitable[None]]

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ReplyTarget:
    """Minimal Telegram routing data retained while work is outstanding."""

    bot: Bot | None
    chat_id: int
    message_id: int


@dataclass(slots=True)
class _BacklogState:
    count: int
    target: ReplyTarget
    text: str
    timer: asyncio.Task[None]


@dataclass(slots=True)
class _ActivityState:
    count: int
    stop: asyncio.Event
    task: asyncio.Task[None]


class TelegramProgressCoordinator:
    """Coalesce progress by user backlog and active private chat."""

    def __init__(
        self,
        *,
        wait_notice_seconds: float = 5.0,
        activity_interval_seconds: float = 4.0,
        coalesce_seconds: float = 5.0,
        max_activity_backoff_seconds: float = 30.0,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self._wait_notice_seconds = wait_notice_seconds
        self._activity_interval_seconds = activity_interval_seconds
        self._coalesce_seconds = coalesce_seconds
        self._max_activity_backoff_seconds = max_activity_backoff_seconds
        self._sleep = sleep
        self._lock = asyncio.Lock()
        self._backlogs: dict[tuple[int, int], _BacklogState] = {}
        self._activities: dict[tuple[Bot, int], _ActivityState] = {}
        self._cooldowns: dict[tuple[int, str], asyncio.Task[None]] = {}
        self._closed = False

    async def enter_backlog(
        self,
        *,
        user_id: int,
        backlog_id: int,
        target: ReplyTarget,
        text: str,
    ) -> None:
        """Register one waiting job and start one timer for its backlog episode."""
        key = (user_id, backlog_id)
        async with self._lock:
            if self._closed:
                return
            state = self._backlogs.get(key)
            if state is not None:
                state.count += 1
                return
            timer = asyncio.create_task(self._notify_backlog_after_delay(key))
            self._backlogs[key] = _BacklogState(
                count=1,
                target=target,
                text=text,
                timer=timer,
            )

    async def leave_backlog(self, *, user_id: int, backlog_id: int) -> None:
        """Remove one waiting job and reset the episode when its backlog empties."""
        key = (user_id, backlog_id)
        timer: asyncio.Task[None] | None = None
        async with self._lock:
            state = self._backlogs.get(key)
            if state is None:
                return
            state.count -= 1
            if state.count > 0:
                return
            del self._backlogs[key]
            timer = state.timer
            if timer is not asyncio.current_task():
                timer.cancel()
        if timer is not None and timer is not asyncio.current_task():
            await asyncio.gather(timer, return_exceptions=True)

    async def send_coalesced(
        self,
        *,
        user_id: int,
        kind: str,
        target: ReplyTarget,
        text: str,
    ) -> None:
        """Send at most one response kind per user during the cooldown window."""
        key = (user_id, kind)
        async with self._lock:
            if self._closed or key in self._cooldowns:
                return
            cooldown = asyncio.create_task(self._clear_cooldown_after_delay(key))
            self._cooldowns[key] = cooldown
        await self._safe_reply(target, text, response_kind=kind)

    @asynccontextmanager
    async def rendering(self, target: ReplyTarget) -> AsyncIterator[None]:
        """Hold one reference on the chat-scoped active-render activity loop."""
        key: tuple[Bot, int] | None = None
        bot = target.bot
        if bot is not None:
            key = (bot, target.chat_id)
            async with self._lock:
                if not self._closed:
                    state = self._activities.get(key)
                    if state is None:
                        stop = asyncio.Event()
                        task = asyncio.create_task(
                            self._run_activity(
                                bot=bot,
                                chat_id=target.chat_id,
                                stop=stop,
                            )
                        )
                        self._activities[key] = _ActivityState(
                            count=1,
                            stop=stop,
                            task=task,
                        )
                    else:
                        state.count += 1
                else:
                    key = None
            await asyncio.sleep(0)
        try:
            yield
        finally:
            if key is not None:
                await self._release_activity(key)

    async def close(self) -> None:
        """Stop outstanding timers and activity loops exactly once."""
        async with self._lock:
            if self._closed:
                return
            self._closed = True
            backlog_tasks = [state.timer for state in self._backlogs.values()]
            cooldown_tasks = list(self._cooldowns.values())
            activity_states = list(self._activities.values())
            self._backlogs.clear()
            self._cooldowns.clear()
            self._activities.clear()
            for task in (*backlog_tasks, *cooldown_tasks):
                task.cancel()
            for state in activity_states:
                state.stop.set()
        await asyncio.gather(
            *backlog_tasks,
            *cooldown_tasks,
            *(state.task for state in activity_states),
            return_exceptions=True,
        )

    async def _notify_backlog_after_delay(self, key: tuple[int, int]) -> None:
        try:
            await self._sleep(self._wait_notice_seconds)
        except asyncio.CancelledError:
            return
        async with self._lock:
            state = self._backlogs.get(key)
            if state is None or state.count <= 0 or self._closed:
                return
            target = state.target
            text = state.text
        await self._safe_reply(target, text, response_kind="queue_wait")

    async def _clear_cooldown_after_delay(self, key: tuple[int, str]) -> None:
        try:
            await self._sleep(self._coalesce_seconds)
        except asyncio.CancelledError:
            return
        async with self._lock:
            self._cooldowns.pop(key, None)

    async def _release_activity(self, key: tuple[Bot, int]) -> None:
        task: asyncio.Task[None] | None = None
        async with self._lock:
            state = self._activities.get(key)
            if state is None:
                return
            state.count -= 1
            if state.count > 0:
                return
            del self._activities[key]
            state.stop.set()
            task = state.task
        await asyncio.gather(task, return_exceptions=True)

    async def _run_activity(
        self,
        *,
        bot: Bot,
        chat_id: int,
        stop: asyncio.Event,
    ) -> None:
        delay = 0.0
        failure_backoff = self._activity_interval_seconds
        while not stop.is_set():
            if delay > 0 and await self._wait_for_stop(stop, delay):
                return
            try:
                await bot.send_chat_action(
                    chat_id=chat_id,
                    action=ChatAction.RECORD_VOICE,
                )
            except TelegramRetryAfter as error:
                logger.warning(
                    "chat_action_rate_limited action=record_voice retry_after_seconds=%s",
                    error.retry_after,
                )
                delay = max(float(error.retry_after), self._activity_interval_seconds)
            except Exception as error:
                logger.warning(
                    "chat_action_failed action=record_voice exception_type=%s",
                    type(error).__name__,
                )
                delay = failure_backoff
                failure_backoff = min(
                    failure_backoff * 2,
                    self._max_activity_backoff_seconds,
                )
            else:
                delay = self._activity_interval_seconds
                failure_backoff = self._activity_interval_seconds

    async def _wait_for_stop(self, stop: asyncio.Event, delay: float) -> bool:
        wait_task = asyncio.create_task(stop.wait())
        sleep_task: asyncio.Future[None] = asyncio.ensure_future(self._sleep(delay))
        tasks: set[asyncio.Future[Any]] = {wait_task, sleep_task}
        done, pending = await asyncio.wait(
            tasks,
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        return wait_task in done and bool(wait_task.result())

    @staticmethod
    async def _safe_reply(target: ReplyTarget, text: str, *, response_kind: str) -> None:
        bot = target.bot
        if bot is None:
            logger.warning(
                "text_response_skipped response_kind=%s reason=bot_unbound",
                response_kind,
            )
            return
        try:
            await bot.send_message(
                chat_id=target.chat_id,
                text=text,
                reply_parameters=ReplyParameters(message_id=target.message_id),
            )
        except Exception as error:
            logger.error(
                "text_response_failed response_kind=%s exception_type=%s",
                response_kind,
                type(error).__name__,
            )
