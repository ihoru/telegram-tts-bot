import asyncio
from collections.abc import Sequence
from typing import cast

import pytest

from telegram_tts_bot.bot_service import (
    BotSpeechService,
    RejectionReason,
    RenderedVoice,
    RenderRejected,
)
from telegram_tts_bot.speech import VoiceAudio, VoiceRenderer


class ControlledRenderer:
    def __init__(self, *, failures: Sequence[Exception] = ()) -> None:
        self.texts: list[str] = []
        self.started: asyncio.Queue[None] = asyncio.Queue()
        self.release = asyncio.Event()
        self.closed = False
        self._failures = list(failures)

    async def render(self, text: str, /) -> VoiceAudio:
        self.texts.append(text)
        self.started.put_nowait(None)
        await self.release.wait()
        if self._failures:
            raise self._failures.pop(0)
        return VoiceAudio(data=text.encode(), filename="voice.ogg")

    async def close(self) -> None:
        self.closed = True


def make_service(
    renderer: ControlledRenderer,
    *,
    global_limit: int = 5,
    per_user_limit: int = 1,
) -> BotSpeechService:
    return BotSpeechService(
        cast(VoiceRenderer, renderer),
        global_limit=global_limit,
        per_user_limit=per_user_limit,
    )


async def test_per_user_capacity_rejects_immediately_without_queueing() -> None:
    renderer = ControlledRenderer()
    service = make_service(renderer)
    first = asyncio.create_task(service.try_render(user_id=7, text="first"))
    await renderer.started.get()

    second = await asyncio.wait_for(service.try_render(user_id=7, text="second"), timeout=0.1)

    assert second == RenderRejected(RejectionReason.USER_CAPACITY)
    assert renderer.texts == ["first"]
    renderer.release.set()
    assert isinstance(await first, RenderedVoice)
    await service.close()


async def test_global_capacity_is_distinct_from_per_user_capacity() -> None:
    renderer = ControlledRenderer()
    service = make_service(renderer, global_limit=2)
    active = [
        asyncio.create_task(service.try_render(user_id=user_id, text=str(user_id)))
        for user_id in (1, 2)
    ]
    await renderer.started.get()
    await renderer.started.get()

    rejected = await asyncio.wait_for(service.try_render(user_id=3, text="three"), timeout=0.1)

    assert rejected == RenderRejected(RejectionReason.GLOBAL_CAPACITY)
    renderer.release.set()
    await asyncio.gather(*active)
    await service.close()


async def test_renderer_failure_releases_capacity() -> None:
    renderer = ControlledRenderer(failures=[RuntimeError("safe failure")])
    renderer.release.set()
    service = make_service(renderer)

    with pytest.raises(RuntimeError, match="safe failure"):
        await service.try_render(user_id=9, text="first")

    second = await service.try_render(user_id=9, text="second")
    assert isinstance(second, RenderedVoice)
    await service.close()


async def test_cancelled_caller_keeps_slot_until_renderer_finishes() -> None:
    renderer = ControlledRenderer()
    service = make_service(renderer)
    active = asyncio.create_task(service.try_render(user_id=4, text="active"))
    await renderer.started.get()

    active.cancel()
    with pytest.raises(asyncio.CancelledError):
        await active

    while_running = await service.try_render(user_id=4, text="too soon")
    assert while_running == RenderRejected(RejectionReason.USER_CAPACITY)

    renderer.release.set()
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    accepted = await service.try_render(user_id=4, text="after")
    assert isinstance(accepted, RenderedVoice)
    await service.close()


async def test_close_stops_intake_and_waits_for_active_renderer() -> None:
    renderer = ControlledRenderer()
    service = make_service(renderer)
    active = asyncio.create_task(service.try_render(user_id=1, text="active"))
    await renderer.started.get()
    closing = asyncio.create_task(service.close())
    await asyncio.sleep(0)

    assert not closing.done()
    assert await service.try_render(user_id=2, text="late") == RenderRejected(
        RejectionReason.GLOBAL_CAPACITY
    )

    renderer.release.set()
    await active
    await closing
    assert renderer.closed
    await service.close()


@pytest.mark.parametrize(
    ("global_limit", "per_user_limit"),
    [(0, 1), (1, 0), (1, 2)],
)
def test_invalid_service_limits_fail_fast(global_limit: int, per_user_limit: int) -> None:
    renderer = ControlledRenderer()

    with pytest.raises(ValueError, match="invalid admission limits"):
        make_service(
            renderer,
            global_limit=global_limit,
            per_user_limit=per_user_limit,
        )
