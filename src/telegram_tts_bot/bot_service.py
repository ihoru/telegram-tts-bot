"""Bounded fair queueing and rendering orchestration for Telegram requests."""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum

from telegram_tts_bot.speech import VoiceAudio, VoiceRenderer

Clock = Callable[[], float]
Sleep = Callable[[float], Awaitable[None]]


class RejectionReason(StrEnum):
    """Reason a render request was rejected without entering the queue."""

    GLOBAL_QUEUE_FULL = "global_queue_full"
    USER_QUEUE_FULL = "user_queue_full"
    SHUTTING_DOWN = "shutting_down"


class AbortReason(StrEnum):
    """Reason accepted waiting work ended before rendering started."""

    EXPIRED = "expired"
    SHUTDOWN = "shutdown"


@dataclass(frozen=True, slots=True)
class RenderedVoice:
    """A rendered voice payload and its monotonic timing measurements."""

    audio: VoiceAudio
    queue_duration_seconds: float
    render_duration_seconds: float


@dataclass(frozen=True, slots=True)
class RenderRejected:
    """An immediately rejected render submission."""

    reason: RejectionReason


@dataclass(frozen=True, slots=True)
class RenderAborted:
    """Accepted work that ended before rendering began."""

    reason: AbortReason


RenderOutcome = RenderedVoice | RenderAborted


class RenderJob:
    """Small caller interface for one accepted render request."""

    def __init__(
        self,
        *,
        owner: BotSpeechService,
        user_id: int,
        text: str,
        accepted_at: float,
        backlog_id: int | None,
    ) -> None:
        loop = asyncio.get_running_loop()
        self._owner = owner
        self._user_id = user_id
        self._text: str | None = text
        self._accepted_at = accepted_at
        self._start_future: asyncio.Future[RenderAborted | None] = loop.create_future()
        self._result_future: asyncio.Future[RenderOutcome] = loop.create_future()
        self._result_future.add_done_callback(_consume_future_exception)
        self._expiry_task: asyncio.Task[None] | None = None
        self._active = False
        self._waiting = False
        self.backlog_id = backlog_id

    @property
    def user_id(self) -> int:
        """Return the numeric owner used for capacity and fairness."""
        return self._user_id

    @property
    def was_queued(self) -> bool:
        """Return whether this job entered the waiting queue."""
        return self.backlog_id is not None

    async def wait_started(self) -> RenderAborted | None:
        """Wait until rendering starts or waiting ends before start."""
        try:
            return await asyncio.shield(self._start_future)
        except asyncio.CancelledError:
            await self._owner.cancel(self)
            raise

    async def result(self) -> RenderOutcome:
        """Wait for the rendered payload or a pre-render abort."""
        try:
            return await asyncio.shield(self._result_future)
        except asyncio.CancelledError:
            await self._owner.cancel(self)
            raise


SubmissionResult = RenderJob | RenderRejected


class BotSpeechService:
    """Own a bounded fair queue behind a small render-job interface."""

    def __init__(
        self,
        renderer: VoiceRenderer,
        *,
        global_limit: int,
        per_user_limit: int,
        queue_limit: int,
        per_user_queue_limit: int,
        queue_wait_seconds: float,
        clock: Clock = time.monotonic,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        if global_limit <= 0 or per_user_limit <= 0 or per_user_limit > global_limit:
            raise ValueError("invalid active limits")
        if queue_limit <= 0 or per_user_queue_limit <= 0 or per_user_queue_limit > queue_limit:
            raise ValueError("invalid queue limits")
        if queue_wait_seconds <= 0:
            raise ValueError("invalid queue wait")

        self._renderer = renderer
        self._global_limit = global_limit
        self._per_user_limit = per_user_limit
        self._queue_limit = queue_limit
        self._per_user_queue_limit = per_user_queue_limit
        self._queue_wait_seconds = queue_wait_seconds
        self._clock = clock
        self._sleep = sleep

        self._lock = asyncio.Lock()
        self._close_lock = asyncio.Lock()
        self._active_zero = asyncio.Event()
        self._active_zero.set()
        self._accepting = True
        self._closed = False
        self._active = 0
        self._active_by_user: dict[int, int] = {}
        self._waiting = 0
        self._waiting_by_user: dict[int, deque[RenderJob]] = {}
        self._rotation: deque[int] = deque()
        self._next_backlog_id = 1
        self._backlog_by_user: dict[int, int] = {}
        self._render_tasks: set[asyncio.Task[None]] = set()
        self._expiry_tasks: set[asyncio.Task[None]] = set()

    async def submit(self, *, user_id: int, text: str) -> SubmissionResult:
        """Accept active work or enqueue it within strict waiting limits."""
        async with self._lock:
            if not self._accepting:
                return RenderRejected(RejectionReason.SHUTTING_DOWN)

            accepted_at = self._clock()
            if self._can_start_locked(user_id):
                job = RenderJob(
                    owner=self,
                    user_id=user_id,
                    text=text,
                    accepted_at=accepted_at,
                    backlog_id=None,
                )
                self._start_locked(job)
                return job

            user_queue = self._waiting_by_user.get(user_id)
            user_waiting = len(user_queue) if user_queue is not None else 0
            if user_waiting >= self._per_user_queue_limit:
                return RenderRejected(RejectionReason.USER_QUEUE_FULL)
            if self._waiting >= self._queue_limit:
                return RenderRejected(RejectionReason.GLOBAL_QUEUE_FULL)

            backlog_id = self._backlog_by_user.get(user_id)
            if backlog_id is None:
                backlog_id = self._next_backlog_id
                self._next_backlog_id += 1
                self._backlog_by_user[user_id] = backlog_id
            job = RenderJob(
                owner=self,
                user_id=user_id,
                text=text,
                accepted_at=accepted_at,
                backlog_id=backlog_id,
            )
            job._waiting = True
            if user_queue is None:
                user_queue = deque()
                self._waiting_by_user[user_id] = user_queue
                self._rotation.append(user_id)
            user_queue.append(job)
            self._waiting += 1
            expiry_task = asyncio.create_task(self._expire_after_wait(job))
            job._expiry_task = expiry_task
            self._expiry_tasks.add(expiry_task)
            expiry_task.add_done_callback(self._expiry_tasks.discard)
            return job

    async def cancel(self, job: RenderJob) -> None:
        """Remove caller-abandoned waiting work without cancelling active rendering."""
        async with self._lock:
            if not job._waiting:
                return
            self._remove_waiting_locked(job)
            self._finish_before_start_locked(job, AbortReason.SHUTDOWN)
            self._schedule_locked()

    async def begin_shutdown(self) -> None:
        """Stop intake and wake every waiting caller with a shutdown outcome."""
        async with self._lock:
            if not self._accepting:
                return
            self._accepting = False
            queued = [job for queue in self._waiting_by_user.values() for job in queue]
            self._waiting_by_user.clear()
            self._rotation.clear()
            self._backlog_by_user.clear()
            self._waiting = 0
            for job in queued:
                job._waiting = False
                self._cancel_expiry_locked(job)
                self._finish_before_start_locked(job, AbortReason.SHUTDOWN)

    async def close(self) -> None:
        """Stop intake, await active renders, and close the renderer exactly once."""
        async with self._close_lock:
            if self._closed:
                return
            await self.begin_shutdown()
            await self._active_zero.wait()
            if self._render_tasks:
                await asyncio.gather(*tuple(self._render_tasks))
            if self._expiry_tasks:
                await asyncio.gather(*tuple(self._expiry_tasks), return_exceptions=True)
            await self._renderer.close()
            self._closed = True

    def _can_start_locked(self, user_id: int) -> bool:
        return (
            self._active < self._global_limit
            and self._active_by_user.get(user_id, 0) < self._per_user_limit
        )

    def _start_locked(self, job: RenderJob) -> None:
        job._waiting = False
        job._active = True
        self._cancel_expiry_locked(job)
        self._active += 1
        self._active_by_user[job.user_id] = self._active_by_user.get(job.user_id, 0) + 1
        self._active_zero.clear()
        queue_duration = max(0.0, self._clock() - job._accepted_at)
        if not job._start_future.done():
            job._start_future.set_result(None)
        render_task = asyncio.create_task(self._run_render(job, queue_duration))
        self._render_tasks.add(render_task)
        render_task.add_done_callback(self._render_tasks.discard)

    async def _run_render(self, job: RenderJob, queue_duration: float) -> None:
        text = job._text
        job._text = None
        if text is None:
            raise RuntimeError("render job text released before start")
        render_started = self._clock()
        try:
            audio = await self._renderer.render(text)
        except BaseException as error:
            if not job._result_future.done():
                job._result_future.set_exception(error)
        else:
            rendered = RenderedVoice(
                audio=audio,
                queue_duration_seconds=queue_duration,
                render_duration_seconds=max(0.0, self._clock() - render_started),
            )
            if not job._result_future.done():
                job._result_future.set_result(rendered)
        finally:
            async with self._lock:
                self._release_active_locked(job)
                self._schedule_locked()

    def _release_active_locked(self, job: RenderJob) -> None:
        if not job._active:
            raise RuntimeError("active render released more than once")
        job._active = False
        user_active = self._active_by_user[job.user_id]
        if user_active == 1:
            del self._active_by_user[job.user_id]
        else:
            self._active_by_user[job.user_id] = user_active - 1
        self._active -= 1
        if self._active == 0:
            self._active_zero.set()

    def _schedule_locked(self) -> None:
        while self._active < self._global_limit and self._rotation:
            eligible_job: RenderJob | None = None
            users_to_scan = len(self._rotation)
            for _ in range(users_to_scan):
                user_id = self._rotation.popleft()
                queue = self._waiting_by_user.get(user_id)
                if not queue:
                    continue
                if self._active_by_user.get(user_id, 0) >= self._per_user_limit:
                    self._rotation.append(user_id)
                    continue
                eligible_job = queue.popleft()
                self._waiting -= 1
                if queue:
                    self._rotation.append(user_id)
                else:
                    del self._waiting_by_user[user_id]
                    self._backlog_by_user.pop(user_id, None)
                break
            if eligible_job is None:
                return
            if self._clock() - eligible_job._accepted_at >= self._queue_wait_seconds:
                eligible_job._waiting = False
                self._cancel_expiry_locked(eligible_job)
                self._finish_before_start_locked(eligible_job, AbortReason.EXPIRED)
                continue
            self._start_locked(eligible_job)

    async def _expire_after_wait(self, job: RenderJob) -> None:
        try:
            await self._sleep(self._queue_wait_seconds)
        except asyncio.CancelledError:
            return
        async with self._lock:
            if not job._waiting:
                return
            self._remove_waiting_locked(job)
            self._finish_before_start_locked(job, AbortReason.EXPIRED)
            self._schedule_locked()

    def _remove_waiting_locked(self, job: RenderJob) -> None:
        queue = self._waiting_by_user.get(job.user_id)
        if queue is None:
            raise RuntimeError("waiting render missing from user queue")
        queue.remove(job)
        job._waiting = False
        self._waiting -= 1
        self._cancel_expiry_locked(job)
        if not queue:
            del self._waiting_by_user[job.user_id]
            self._backlog_by_user.pop(job.user_id, None)
            self._rotation.remove(job.user_id)

    def _finish_before_start_locked(self, job: RenderJob, reason: AbortReason) -> None:
        job._text = None
        aborted = RenderAborted(reason)
        if not job._start_future.done():
            job._start_future.set_result(aborted)
        if not job._result_future.done():
            job._result_future.set_result(aborted)

    @staticmethod
    def _cancel_expiry_locked(job: RenderJob) -> None:
        task = job._expiry_task
        job._expiry_task = None
        if task is not None and task is not asyncio.current_task():
            task.cancel()


def _consume_future_exception(future: asyncio.Future[RenderOutcome]) -> None:
    if future.cancelled():
        return
    future.exception()
