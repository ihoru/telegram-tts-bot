import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, cast

import pytest
from aiogram import Bot
from aiogram.enums import ChatType
from aiogram.types import BufferedInputFile, Chat, Message, Update, User

from telegram_tts_bot.activity import HandlerActivity
from telegram_tts_bot.bot_service import (
    BotSpeechService,
    RejectionReason,
    RenderedVoice,
    RenderRejected,
)
from telegram_tts_bot.handlers import (
    MAX_TELEGRAM_TEXT_LENGTH,
    PrivateChatFilter,
    TextMessageFilter,
    create_router,
    handle_help,
    handle_start,
    handle_text,
    handle_unsupported,
)
from telegram_tts_bot.localization import Locale, MessageKey, message_text
from telegram_tts_bot.runtime import create_dispatcher
from telegram_tts_bot.speech import VoiceAudio

MESSAGE_DATE = datetime(2026, 8, 27, tzinfo=UTC)


@dataclass
class FakeUser:
    id: int = 42
    language_code: str | None = "en"


@dataclass
class FakeMessage:
    text: str | None = None
    caption: str | None = None
    forward_origin: object | None = None
    answers: list[str] = field(default_factory=list)
    replies: list[str] = field(default_factory=list)
    voices: list[BufferedInputFile] = field(default_factory=list)
    send_error: Exception | None = None

    async def answer(self, text: str) -> None:
        if self.send_error is not None:
            raise self.send_error
        self.answers.append(text)

    async def reply(self, text: str) -> None:
        if self.send_error is not None:
            raise self.send_error
        self.replies.append(text)

    async def reply_voice(self, voice: BufferedInputFile) -> None:
        if self.send_error is not None:
            raise self.send_error
        self.voices.append(voice)


class StubSpeechService:
    def __init__(self, result: RenderedVoice | RenderRejected | Exception) -> None:
        self.result = result
        self.calls: list[tuple[int, str]] = []

    async def try_render(self, *, user_id: int, text: str) -> RenderedVoice | RenderRejected:
        self.calls.append((user_id, text))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def as_message(message: FakeMessage) -> Message:
    return cast(Message, cast(Any, message))


def as_user(user: FakeUser) -> User:
    return cast(User, cast(Any, user))


def as_service(service: StubSpeechService) -> BotSpeechService:
    return cast(BotSpeechService, cast(Any, service))


async def test_start_and_help_use_sender_locale() -> None:
    russian = FakeMessage()
    english = FakeMessage()

    await handle_start(as_message(russian), as_user(FakeUser(language_code="ru-RU")))
    await handle_help(as_message(english), as_user(FakeUser(language_code=None)))

    assert russian.answers == [message_text(Locale.RU, MessageKey.START)]
    assert english.answers == [message_text(Locale.EN, MessageKey.HELP)]


@pytest.mark.parametrize("forward_origin", [None, "visible-user", "privacy-hidden"])
async def test_direct_copied_and_forwarded_text_use_exact_same_path(
    forward_origin: str | None,
) -> None:
    supplied_text = "  Точный текст без метаданных  "
    message = FakeMessage(text=supplied_text, forward_origin=forward_origin)
    service = StubSpeechService(RenderedVoice(VoiceAudio(b"ogg")))

    await handle_text(
        as_message(message),
        as_user(FakeUser(id=88, language_code="ru")),
        as_service(service),
    )

    assert service.calls == [(88, supplied_text)]
    assert len(message.voices) == 1
    assert message.voices[0].data == b"ogg"
    assert message.voices[0].filename == "voice.ogg"


@pytest.mark.parametrize(
    ("reason", "key"),
    [
        (RejectionReason.USER_CAPACITY, MessageKey.USER_BUSY),
        (RejectionReason.GLOBAL_CAPACITY, MessageKey.GLOBAL_BUSY),
    ],
)
async def test_capacity_rejections_have_distinct_localized_responses(
    reason: RejectionReason,
    key: MessageKey,
) -> None:
    message = FakeMessage(text="hello")
    service = StubSpeechService(RenderRejected(reason))

    await handle_text(as_message(message), as_user(FakeUser()), as_service(service))

    assert message.replies == [message_text(Locale.EN, key)]
    assert not message.voices


@pytest.mark.parametrize(
    ("text", "key"),
    [
        (" \n\t", MessageKey.EMPTY_TEXT),
        ("x" * (MAX_TELEGRAM_TEXT_LENGTH + 1), MessageKey.TEXT_TOO_LONG),
    ],
)
async def test_invalid_bot_text_is_rejected_before_rendering(text: str, key: MessageKey) -> None:
    message = FakeMessage(text=text)
    service = StubSpeechService(RenderedVoice(VoiceAudio(b"unused")))

    await handle_text(as_message(message), as_user(FakeUser()), as_service(service))

    assert service.calls == []
    assert message.replies == [message_text(Locale.EN, key)]


async def test_unsupported_caption_gets_guidance_without_rendering() -> None:
    message = FakeMessage(text=None, caption="forwarded caption", forward_origin="visible-user")

    await handle_unsupported(as_message(message), as_user(FakeUser(language_code="ru")))

    assert message.replies == [message_text(Locale.RU, MessageKey.UNSUPPORTED)]


async def test_private_and_text_filters_ignore_group_and_caption_content() -> None:
    private_text = Message(
        message_id=1,
        date=MESSAGE_DATE,
        chat=Chat(id=1, type=ChatType.PRIVATE),
        text="text",
    )
    group_text = Message(
        message_id=2,
        date=MESSAGE_DATE,
        chat=Chat(id=-1, type=ChatType.GROUP),
        text="text",
    )
    private_caption = Message(
        message_id=3,
        date=MESSAGE_DATE,
        chat=Chat(id=1, type=ChatType.PRIVATE),
        caption="caption",
    )

    assert await PrivateChatFilter()(private_text)
    assert not await PrivateChatFilter()(group_text)
    assert await TextMessageFilter()(private_text)
    assert not await TextMessageFilter()(private_caption)


async def test_dispatcher_routes_real_private_message_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = StubSpeechService(RenderedVoice(VoiceAudio(b"ogg")))
    dispatcher = create_dispatcher(as_service(service), HandlerActivity())
    sent_voices: list[BufferedInputFile] = []

    async def capture_voice(_message: Message, voice: BufferedInputFile) -> None:
        sent_voices.append(voice)
        await asyncio.sleep(0)

    monkeypatch.setattr(Message, "reply_voice", capture_voice)
    bot = Bot(token="123456:local-test-token")
    update = Update(
        update_id=1,
        message=Message(
            message_id=10,
            date=MESSAGE_DATE,
            chat=Chat(id=88, type=ChatType.PRIVATE),
            from_user=User(
                id=88,
                is_bot=False,
                first_name="Test",
                language_code="en",
            ),
            text="Прочитай это",
        ),
    )

    try:
        await dispatcher.feed_update(bot, update)
    finally:
        await bot.session.close()

    assert service.calls == [(88, "Прочитай это")]
    assert [voice.data for voice in sent_voices] == [b"ogg"]


async def test_render_failure_logs_only_safe_diagnostics(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret_text = "highly private source text"
    hidden_sender = "Hidden Person"
    message = FakeMessage(text=secret_text, forward_origin=hidden_sender)
    service = StubSpeechService(RuntimeError(secret_text))

    with caplog.at_level(logging.ERROR):
        await handle_text(as_message(message), as_user(FakeUser()), as_service(service))

    assert message.replies == [message_text(Locale.EN, MessageKey.RENDER_FAILED)]
    assert secret_text not in caplog.text
    assert hidden_sender not in caplog.text
    assert "RuntimeError" in caplog.text


async def test_success_log_reports_render_duration_without_source_text(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_text = "private render timing sentinel"
    message = FakeMessage(text=source_text)
    service = StubSpeechService(RenderedVoice(VoiceAudio(b"audio")))
    clock_values = iter((100.0, 101.23456))
    monkeypatch.setattr(time, "perf_counter", lambda: next(clock_values))

    with caplog.at_level(logging.INFO):
        await handle_text(as_message(message), as_user(FakeUser()), as_service(service))

    assert "speech_rendered" in caplog.text
    assert "render_duration_seconds=1.235" in caplog.text
    assert source_text not in caplog.text


async def test_upload_failure_is_not_retried_or_logged_with_content(
    caplog: pytest.LogCaptureFixture,
) -> None:
    source_text = "never put this in logs"
    message = FakeMessage(text=source_text, send_error=RuntimeError(source_text))
    service = StubSpeechService(RenderedVoice(VoiceAudio(b"audio")))

    with caplog.at_level(logging.ERROR):
        await handle_text(as_message(message), as_user(FakeUser()), as_service(service))

    assert source_text not in caplog.text
    assert "voice_upload_failed" in caplog.text


async def test_text_response_failure_is_privacy_safe(caplog: pytest.LogCaptureFixture) -> None:
    message = FakeMessage(send_error=RuntimeError("response contents"))

    with caplog.at_level(logging.ERROR):
        await handle_start(as_message(message), as_user(FakeUser()))

    assert "response contents" not in caplog.text
    assert "response_kind=start" in caplog.text


def test_router_registers_private_commands_text_and_fallback_in_order() -> None:
    router = create_router()

    assert router.name == "telegram_tts_bot.handlers"
    assert len(router.message.handlers) == 4
    filters = router.message._handler.filters
    assert filters is not None
    assert len(filters) == 1
    assert filters[0].awaitable
    assert all(
        filter_object.awaitable
        for handler in router.message.handlers
        for filter_object in (handler.filters or ())
    )
