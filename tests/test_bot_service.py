import asyncio
from dataclasses import dataclass
from typing import cast

import pytest

from telegram_tts_bot.bot_service import (
    AbortReason,
    BotSpeechService,
    RejectionReason,
    RenderAborted,
    RenderedVoice,
    RenderJob,
    RenderRejected,
)
from telegram_tts_bot.speech import VoiceAudio, VoiceRenderer


class ControlledRenderer:
    def __init__(self, *, failures: dict[str, Exception] | None = None) -> None:
        self.texts: list[str] = []
        self.started: asyncio.Queue[str] = asyncio.Queue()
        self.closed = False
        self._releases: dict[str, asyncio.Event] = {}
        self._failures = failures or {}

    async def render(self, text: str, /) -> VoiceAudio:
        self.texts.append(text)
        self.started.put_nowait(text)
        await self._releases.setdefault(text, asyncio.Event()).wait()
        failure = self._failures.get(text)
        if failure is not None:
            raise failure
        return VoiceAudio(data=text.encode(), filename="voice.ogg")

    def release(self, text: str) -> None:
        self._releases.setdefault(text, asyncio.Event()).set()

    async def close(self) -> None:
        self.closed = True


class ManualSleep:
    def __init__(self) -> None:
        self.calls: asyncio.Queue[tuple[float, asyncio.Event]] = asyncio.Queue()

    async def __call__(self, delay: float) -> None:
        release = asyncio.Event()
        self.calls.put_nowait((delay, release))
        await release.wait()


@dataclass
class ManualClock:
    value: float = 0.0

    def __call__(self) -> float:
        return self.value


def make_service(
    renderer: ControlledRenderer,
    *,
    global_limit: int = 1,
    per_user_limit: int = 1,
    queue_limit: int = 20,
    per_user_queue_limit: int = 10,
    queue_wait_seconds: float = 600,
    clock: ManualClock | None = None,
    sleep: ManualSleep | None = None,
) -> BotSpeechService:
    return BotSpeechService(
        cast(VoiceRenderer, renderer),
        global_limit=global_limit,
        per_user_limit=per_user_limit,
        queue_limit=queue_limit,
        per_user_queue_limit=per_user_queue_limit,
        queue_wait_seconds=queue_wait_seconds,
        clock=clock or ManualClock(),
        sleep=sleep or ManualSleep(),
    )


async def accepted_job(result: RenderJob | RenderRejected) -> RenderJob:
    await asyncio.sleep(0)
    assert isinstance(result, RenderJob)
    return result


async def finish(renderer: ControlledRenderer, job: RenderJob, text: str) -> RenderedVoice:
    assert await renderer.started.get() == text
    renderer.release(text)
    result = await job.result()
    assert isinstance(result, RenderedVoice)
    return result


async def test_immediate_render_and_per_user_fifo_queue() -> None:
    renderer = ControlledRenderer()
    service = make_service(renderer)
    first = await accepted_job(await service.submit(user_id=7, text="first"))
    second = await accepted_job(await service.submit(user_id=7, text="second"))
    third = await accepted_job(await service.submit(user_id=7, text="third"))

    assert not first.was_queued
    assert second.was_queued and third.was_queued
    assert second.backlog_id == third.backlog_id
    assert await first.wait_started() is None
    await finish(renderer, first, "first")
    assert await second.wait_started() is None
    await finish(renderer, second, "second")
    assert await third.wait_started() is None
    await finish(renderer, third, "third")
    assert renderer.texts == ["first", "second", "third"]
    await service.close()


async def test_round_robin_fairness_preserves_each_users_fifo() -> None:
    renderer = ControlledRenderer()
    service = make_service(renderer)
    active = await accepted_job(await service.submit(user_id=0, text="active"))
    one_a = await accepted_job(await service.submit(user_id=1, text="one-a"))
    one_b = await accepted_job(await service.submit(user_id=1, text="one-b"))
    two_a = await accepted_job(await service.submit(user_id=2, text="two-a"))
    two_b = await accepted_job(await service.submit(user_id=2, text="two-b"))

    for job, text in (
        (active, "active"),
        (one_a, "one-a"),
        (two_a, "two-a"),
        (one_b, "one-b"),
        (two_b, "two-b"),
    ):
        assert await job.wait_started() is None
        await finish(renderer, job, text)

    assert renderer.texts == ["active", "one-a", "two-a", "one-b", "two-b"]
    await service.close()


async def test_scheduler_starts_other_user_when_per_user_slot_is_busy() -> None:
    renderer = ControlledRenderer()
    service = make_service(renderer, global_limit=2)
    one_active = await accepted_job(await service.submit(user_id=1, text="one-active"))
    one_waiting = await accepted_job(await service.submit(user_id=1, text="one-waiting"))
    two_active = await accepted_job(await service.submit(user_id=2, text="two-active"))

    assert await renderer.started.get() == "one-active"
    assert await renderer.started.get() == "two-active"
    renderer.release("two-active")
    assert isinstance(await two_active.result(), RenderedVoice)
    assert not one_waiting._start_future.done()

    renderer.release("one-active")
    assert isinstance(await one_active.result(), RenderedVoice)
    assert await one_waiting.wait_started() is None
    await finish(renderer, one_waiting, "one-waiting")
    await service.close()


async def test_per_user_and_global_queue_limits_reject_newest() -> None:
    renderer = ControlledRenderer()
    service = make_service(renderer, queue_limit=2, per_user_queue_limit=2)
    active = await accepted_job(await service.submit(user_id=0, text="active"))
    await accepted_job(await service.submit(user_id=1, text="one"))
    await accepted_job(await service.submit(user_id=1, text="two"))

    assert await service.submit(user_id=1, text="user-full") == RenderRejected(
        RejectionReason.USER_QUEUE_FULL
    )
    assert await service.submit(user_id=2, text="global-full") == RenderRejected(
        RejectionReason.GLOBAL_QUEUE_FULL
    )
    await service.begin_shutdown()
    renderer.release("active")
    await active.result()
    await service.close()


async def test_waiting_job_expires_without_rendering() -> None:
    renderer = ControlledRenderer()
    sleep = ManualSleep()
    service = make_service(renderer, sleep=sleep)
    active = await accepted_job(await service.submit(user_id=1, text="active"))
    waiting = await accepted_job(await service.submit(user_id=2, text="expired"))
    delay, release_expiry = await sleep.calls.get()

    assert delay == 600
    release_expiry.set()
    assert await waiting.wait_started() == RenderAborted(AbortReason.EXPIRED)
    assert await waiting.result() == RenderAborted(AbortReason.EXPIRED)
    assert renderer.texts == ["active"]

    renderer.release("active")
    await active.result()
    await service.close()


async def test_scheduler_does_not_start_job_at_expiry_deadline() -> None:
    clock = ManualClock()
    renderer = ControlledRenderer()
    service = make_service(renderer, queue_wait_seconds=10, clock=clock)
    active = await accepted_job(await service.submit(user_id=1, text="active"))
    waiting = await accepted_job(await service.submit(user_id=2, text="deadline"))
    assert await renderer.started.get() == "active"

    clock.value = 10
    renderer.release("active")
    assert isinstance(await active.result(), RenderedVoice)
    assert await waiting.wait_started() == RenderAborted(AbortReason.EXPIRED)
    assert "deadline" not in renderer.texts
    await service.close()


async def test_cancelling_waiter_removes_it_from_queue() -> None:
    renderer = ControlledRenderer()
    service = make_service(renderer, queue_limit=1, per_user_queue_limit=1)
    active = await accepted_job(await service.submit(user_id=1, text="active"))
    waiting = await accepted_job(await service.submit(user_id=2, text="cancelled"))
    assert await renderer.started.get() == "active"
    caller = asyncio.create_task(waiting.wait_started())
    await asyncio.sleep(0)

    caller.cancel()
    with pytest.raises(asyncio.CancelledError):
        await caller

    replacement = await service.submit(user_id=3, text="replacement")
    assert isinstance(replacement, RenderJob)
    renderer.release("active")
    await active.result()
    await finish(renderer, replacement, "replacement")
    assert "cancelled" not in renderer.texts
    await service.close()


async def test_cancelled_active_caller_does_not_release_slot_early() -> None:
    renderer = ControlledRenderer()
    service = make_service(renderer)
    active = await accepted_job(await service.submit(user_id=1, text="active"))
    assert await active.wait_started() is None
    caller = asyncio.create_task(active.result())
    assert await renderer.started.get() == "active"
    caller.cancel()
    with pytest.raises(asyncio.CancelledError):
        await caller

    waiting = await accepted_job(await service.submit(user_id=2, text="waiting"))
    assert not waiting._start_future.done()
    renderer.release("active")
    assert await waiting.wait_started() is None
    await finish(renderer, waiting, "waiting")
    await service.close()


async def test_renderer_failure_releases_capacity_and_preserves_timing() -> None:
    clock = ManualClock(10.0)
    renderer = ControlledRenderer(failures={"bad": RuntimeError("safe failure")})
    service = make_service(renderer, clock=clock)
    bad = await accepted_job(await service.submit(user_id=1, text="bad"))
    next_job = await accepted_job(await service.submit(user_id=2, text="next"))
    assert await renderer.started.get() == "bad"
    clock.value = 12.5
    renderer.release("bad")

    with pytest.raises(RuntimeError, match="safe failure"):
        await bad.result()

    assert await next_job.wait_started() is None
    assert await renderer.started.get() == "next"
    clock.value = 15.0
    renderer.release("next")
    result = await next_job.result()
    assert isinstance(result, RenderedVoice)
    assert result.queue_duration_seconds == pytest.approx(2.5)
    assert result.render_duration_seconds == pytest.approx(2.5)
    await service.close()


async def test_shutdown_cancels_waiting_and_finishes_active_before_close() -> None:
    renderer = ControlledRenderer()
    service = make_service(renderer)
    active = await accepted_job(await service.submit(user_id=1, text="active"))
    waiting = await accepted_job(await service.submit(user_id=2, text="waiting"))
    closing = asyncio.create_task(service.close())
    await asyncio.sleep(0)

    assert await waiting.wait_started() == RenderAborted(AbortReason.SHUTDOWN)
    assert not closing.done()
    assert await service.submit(user_id=3, text="late") == RenderRejected(
        RejectionReason.SHUTTING_DOWN
    )

    renderer.release("active")
    assert isinstance(await active.result(), RenderedVoice)
    await closing
    assert renderer.closed
    await service.close()


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"global_limit": 0}, "invalid active limits"),
        ({"per_user_limit": 2}, "invalid active limits"),
        ({"queue_limit": 0}, "invalid queue limits"),
        ({"per_user_queue_limit": 21}, "invalid queue limits"),
        ({"queue_wait_seconds": 0}, "invalid queue wait"),
    ],
)
def test_invalid_service_limits_fail_fast(kwargs: dict[str, float], message: str) -> None:
    renderer = ControlledRenderer()
    with pytest.raises(ValueError, match=message):
        make_service(renderer, **kwargs)  # type: ignore[arg-type]
