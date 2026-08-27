import asyncio
import logging
from collections.abc import Callable
from typing import Any, cast

import pytest
from aiogram import Bot, Dispatcher
from aiogram.types import TelegramObject

from telegram_tts_bot.activity import HandlerActivity, HandlerActivityMiddleware
from telegram_tts_bot.config import BotSettings
from telegram_tts_bot.runtime import configure_logging, create_dispatcher, run_bot
from telegram_tts_bot.speech import VoiceRenderer


async def test_handler_activity_waits_and_rejects_late_intake() -> None:
    activity = HandlerActivity()
    assert await activity.enter()

    stopping = asyncio.create_task(activity.stop_and_wait())
    await asyncio.sleep(0)
    assert not stopping.done()
    assert not await activity.enter()

    await activity.leave()
    await stopping


async def test_activity_middleware_balances_success_and_failure() -> None:
    activity = HandlerActivity()
    middleware = HandlerActivityMiddleware(activity)
    event = cast(TelegramObject, object())

    async def successful(_event: TelegramObject, _data: dict[str, Any]) -> str:
        await asyncio.sleep(0)
        return "handled"

    assert await middleware(successful, event, {}) == "handled"

    async def failing(_event: TelegramObject, _data: dict[str, Any]) -> None:
        await asyncio.sleep(0)
        raise RuntimeError("failure")

    with pytest.raises(RuntimeError, match="failure"):
        await middleware(failing, event, {})

    await activity.stop_and_wait()


class RuntimeRenderer:
    def __init__(self) -> None:
        self.closed = False

    async def render(self, text: str, /) -> Any:
        raise AssertionError(text)

    async def close(self) -> None:
        self.closed = True


class RuntimeSession:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    async def close(self) -> None:
        self.events.append("session_closed")


class RuntimeBot:
    def __init__(self, token: str, events: list[str]) -> None:
        self.token = token
        self.events = events
        self.session = RuntimeSession(events)

    async def delete_webhook(self, *, drop_pending_updates: bool) -> None:
        assert drop_pending_updates is False
        self.events.append("webhook_deleted")


class RuntimeDispatcher:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    async def start_polling(self, bot: Bot, *, close_bot_session: bool) -> None:
        assert close_bot_session is False
        assert bot is not None
        self.events.append("polled")


async def test_run_bot_preserves_updates_and_closes_resources_in_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from telegram_tts_bot import runtime

    events: list[str] = []
    renderer = RuntimeRenderer()
    fake_bot = RuntimeBot("123:token", events)

    def renderer_factory(**kwargs: object) -> VoiceRenderer:
        assert kwargs["max_workers"] == 5
        return cast(VoiceRenderer, renderer)

    def dispatcher_factory(_service: object, _activity: object) -> Dispatcher:
        return cast(Dispatcher, RuntimeDispatcher(events))

    monkeypatch.setattr(runtime, "create_dispatcher", dispatcher_factory)
    settings = BotSettings(telegram_bot_token="123:token")

    await run_bot(
        settings,
        renderer_factory=renderer_factory,
        bot_factory=cast(Callable[[str], Bot], lambda _token: fake_bot),
    )

    assert events == ["webhook_deleted", "polled", "session_closed"]
    assert renderer.closed


async def test_run_bot_closes_session_when_renderer_startup_fails() -> None:
    events: list[str] = []
    fake_bot = RuntimeBot("123:token", events)

    def broken_renderer_factory(**_kwargs: object) -> VoiceRenderer:
        raise RuntimeError("model unavailable")

    with pytest.raises(RuntimeError, match="model unavailable"):
        await run_bot(
            BotSettings(telegram_bot_token="123:token"),
            renderer_factory=broken_renderer_factory,
            bot_factory=cast(Callable[[str], Bot], lambda _token: fake_bot),
        )

    assert events == ["session_closed"]


async def test_run_bot_closes_session_when_renderer_shutdown_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from telegram_tts_bot import runtime

    events: list[str] = []
    fake_bot = RuntimeBot("123:token", events)

    class BrokenCloseRenderer(RuntimeRenderer):
        async def close(self) -> None:
            raise RuntimeError("renderer shutdown failed")

    renderer = BrokenCloseRenderer()

    monkeypatch.setattr(
        runtime,
        "create_dispatcher",
        lambda _service, _activity: cast(Dispatcher, RuntimeDispatcher(events)),
    )

    with pytest.raises(RuntimeError, match="renderer shutdown failed"):
        await run_bot(
            BotSettings(telegram_bot_token="123:token"),
            renderer_factory=lambda **_kwargs: cast(VoiceRenderer, renderer),
            bot_factory=cast(Callable[[str], Bot], lambda _token: fake_bot),
        )

    assert events == ["webhook_deleted", "polled", "session_closed"]


async def test_run_bot_preserves_polling_failure_when_cleanup_also_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from telegram_tts_bot import runtime

    events: list[str] = []
    fake_bot = RuntimeBot("123:token", events)

    class BrokenCloseRenderer(RuntimeRenderer):
        async def close(self) -> None:
            raise RuntimeError("secondary cleanup failure")

    class FailingDispatcher(RuntimeDispatcher):
        async def start_polling(self, bot: Bot, *, close_bot_session: bool) -> None:
            assert not close_bot_session
            raise RuntimeError("primary polling failure")

    monkeypatch.setattr(
        runtime,
        "create_dispatcher",
        lambda _service, _activity: cast(Dispatcher, FailingDispatcher(events)),
    )

    with pytest.raises(RuntimeError, match="primary polling failure"):
        await run_bot(
            BotSettings(telegram_bot_token="123:token"),
            renderer_factory=lambda **_kwargs: cast(VoiceRenderer, BrokenCloseRenderer()),
            bot_factory=cast(Callable[[str], Bot], lambda _token: fake_bot),
        )

    assert events == ["webhook_deleted", "session_closed"]


def test_debug_logging_cannot_emit_piper_source_text(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    piper_logger = logging.getLogger("piper")
    monkeypatch.setattr(piper_logger, "level", logging.NOTSET)
    configure_logging(logging.DEBUG)

    with caplog.at_level(logging.DEBUG):
        logging.getLogger("piper.voice").warning("text=%s", "PRIVATE_MESSAGE_SENTINEL")

    assert piper_logger.level > logging.CRITICAL
    assert "PRIVATE_MESSAGE_SENTINEL" not in caplog.text


def test_create_dispatcher_exposes_speech_service() -> None:
    renderer = RuntimeRenderer()
    from telegram_tts_bot.bot_service import BotSpeechService

    service = BotSpeechService(cast(VoiceRenderer, renderer), global_limit=1, per_user_limit=1)
    dispatcher = create_dispatcher(service, HandlerActivity())

    assert dispatcher.workflow_data["speech_service"] is service
    assert len(dispatcher.sub_routers) == 1
