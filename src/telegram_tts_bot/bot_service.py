"""Admission control and rendering orchestration for Telegram requests."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import StrEnum

from telegram_tts_bot.speech import VoiceAudio, VoiceRenderer


class RejectionReason(StrEnum):
    """Reason a render request was rejected without entering a queue."""

    GLOBAL_CAPACITY = "global_capacity"
    USER_CAPACITY = "user_capacity"


@dataclass(frozen=True, slots=True)
class RenderedVoice:
    """A successfully rendered Telegram voice payload."""

    audio: VoiceAudio


@dataclass(frozen=True, slots=True)
class RenderRejected:
    """An immediately rejected render request."""

    reason: RejectionReason


RenderResult = RenderedVoice | RenderRejected


class _AdmissionGate:
    def __init__(self, *, global_limit: int, per_user_limit: int) -> None:
        if global_limit <= 0 or per_user_limit <= 0 or per_user_limit > global_limit:
            raise ValueError("invalid admission limits")
        self._global_limit = global_limit
        self._per_user_limit = per_user_limit
        self._active = 0
        self._active_by_user: dict[int, int] = {}
        self._accepting = True
        self._condition = asyncio.Condition()

    async def try_acquire(self, user_id: int) -> RejectionReason | None:
        async with self._condition:
            if not self._accepting:
                return RejectionReason.GLOBAL_CAPACITY
            user_active = self._active_by_user.get(user_id, 0)
            if user_active >= self._per_user_limit:
                return RejectionReason.USER_CAPACITY
            if self._active >= self._global_limit:
                return RejectionReason.GLOBAL_CAPACITY
            self._active += 1
            self._active_by_user[user_id] = user_active + 1
            return None

    async def release(self, user_id: int) -> None:
        async with self._condition:
            user_active = self._active_by_user.get(user_id)
            if user_active is None or self._active <= 0:
                raise RuntimeError("admission lease released more than once")
            if user_active == 1:
                del self._active_by_user[user_id]
            else:
                self._active_by_user[user_id] = user_active - 1
            self._active -= 1
            if self._active == 0:
                self._condition.notify_all()

    async def stop_and_wait(self) -> None:
        async with self._condition:
            self._accepting = False
            await self._condition.wait_for(lambda: self._active == 0)


class BotSpeechService:
    """Render accepted work while preserving strict capacity and shutdown rules."""

    def __init__(
        self,
        renderer: VoiceRenderer,
        *,
        global_limit: int,
        per_user_limit: int,
    ) -> None:
        self._renderer = renderer
        self._gate = _AdmissionGate(
            global_limit=global_limit,
            per_user_limit=per_user_limit,
        )
        self._cleanup_tasks: set[asyncio.Task[None]] = set()
        self._close_lock = asyncio.Lock()
        self._closed = False

    async def try_render(self, *, user_id: int, text: str) -> RenderResult:
        """Render immediately when capacity exists; never wait for an admission slot."""
        rejection = await self._gate.try_acquire(user_id)
        if rejection is not None:
            return RenderRejected(rejection)

        render_task = asyncio.create_task(self._render_with_lease(user_id=user_id, text=text))
        try:
            audio = await asyncio.shield(render_task)
        except asyncio.CancelledError:
            cleanup_task = asyncio.create_task(self._consume_after_caller_cancellation(render_task))
            self._cleanup_tasks.add(cleanup_task)
            cleanup_task.add_done_callback(self._cleanup_tasks.discard)
            raise
        return RenderedVoice(audio)

    async def close(self) -> None:
        """Stop new work, await active workers, and close the renderer once."""
        async with self._close_lock:
            if self._closed:
                return
            await self._gate.stop_and_wait()
            if self._cleanup_tasks:
                await asyncio.gather(*tuple(self._cleanup_tasks))
            await self._renderer.close()
            self._closed = True

    async def _render_with_lease(self, *, user_id: int, text: str) -> VoiceAudio:
        try:
            return await self._renderer.render(text)
        finally:
            await self._gate.release(user_id)

    @staticmethod
    async def _consume_after_caller_cancellation(
        render_task: asyncio.Task[VoiceAudio],
    ) -> None:
        try:
            await render_task
        except asyncio.CancelledError:
            pass
        except Exception:
            pass
