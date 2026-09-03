import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, cast

import pytest
from aiogram import Bot
from aiogram.enums import ChatType
from aiogram.types import (
    BufferedInputFile,
    Chat,
    Message,
    ReplyParameters,
    Update,
    User,
)

from telegram_tts_bot.activity import HandlerActivity
from telegram_tts_bot.bot_service import (
    AbortReason,
    BotSpeechService,
    RejectionReason,
    RenderAborted,
    RenderedVoice,
    RenderJob,
    RenderRejected,
)
from telegram_tts_bot.handlers import (
    MAX_TELEGRAM_TEXT_LENGTH,
    PrivateChatFilter,
    TextMessageFilter,
    VoicePresentation,
    create_router,
    handle_help,
    handle_start,
    handle_text,
    handle_unsupported,
)
from telegram_tts_bot.localization import Locale, MessageKey, message_text
from telegram_tts_bot.progress import ReplyTarget, TelegramProgressCoordinator
from telegram_tts_bot.runtime import create_dispatcher
from telegram_tts_bot.speech import VoiceAudio

MESSAGE_DATE = datetime(2026, 8, 27, tzinfo=UTC)
PRESENTATION = VoicePresentation(model_name="Qwen3-TTS", voice_name="aiden")


@dataclass
class FakeUser:
    id: int = 42
    language_code: str | None = "en"


@dataclass(eq=False)
class FakeBot:
    messages: list[tuple[int, str, ReplyParameters | None]] = field(default_factory=list)
    voices: list[tuple[int, BufferedInputFile, str, ReplyParameters | None]] = field(
        default_factory=list
    )
    send_error: Exception | None = None

    async def send_message(
        self,
        *,
        chat_id: int,
        text: str,
        reply_parameters: ReplyParameters | None = None,
    ) -> None:
        if self.send_error is not None:
            raise self.send_error
        self.messages.append((chat_id, text, reply_parameters))

    async def send_voice(
        self,
        *,
        chat_id: int,
        voice: BufferedInputFile,
        caption: str,
        parse_mode: None,
        reply_parameters: ReplyParameters | None = None,
    ) -> None:
        if self.send_error is not None:
            raise self.send_error
        self.voices.append((chat_id, voice, caption, reply_parameters))


@dataclass
class FakeChat:
    id: int = 42


@dataclass
class FakeMessage:
    text: str | None = None
    caption: str | None = None
    forward_origin: object | None = None
    message_id: int = 9
    answers: list[str] = field(default_factory=list)
    replies: list[str] = field(default_factory=list)
    send_error: Exception | None = None
    bot: FakeBot = field(default_factory=FakeBot)
    chat: FakeChat = field(default_factory=FakeChat)

    async def answer(self, text: str) -> None:
        if self.send_error is not None:
            raise self.send_error
        self.answers.append(text)

    async def reply(self, text: str) -> None:
        if self.send_error is not None:
            raise self.send_error
        self.replies.append(text)


class StubJob:
    def __init__(
        self,
        outcome: RenderedVoice | RenderAborted | Exception,
        *,
        backlog_id: int | None = None,
        start_abort: RenderAborted | None = None,
    ) -> None:
        self.outcome = outcome
        self.backlog_id = backlog_id
        self.start_abort = start_abort

    async def wait_started(self) -> RenderAborted | None:
        return self.start_abort

    async def result(self) -> RenderedVoice | RenderAborted:
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


class StubSpeechService:
    def __init__(self, submission: StubJob | RenderRejected) -> None:
        self.submission = submission
        self.calls: list[tuple[int, str]] = []
        self.cancelled: list[StubJob] = []

    async def submit(self, *, user_id: int, text: str) -> RenderJob | RenderRejected:
        self.calls.append((user_id, text))
        return cast(RenderJob | RenderRejected, self.submission)

    async def cancel(self, job: RenderJob) -> None:
        self.cancelled.append(cast(StubJob, cast(Any, job)))


class StubProgress:
    def __init__(self) -> None:
        self.events: list[str] = []
        self.notices: list[tuple[int, str, str]] = []

    async def enter_backlog(self, **kwargs: Any) -> None:
        self.events.append(f"queue_enter:{kwargs['backlog_id']}")

    async def leave_backlog(self, **kwargs: Any) -> None:
        self.events.append(f"queue_leave:{kwargs['backlog_id']}")

    async def send_coalesced(self, **kwargs: Any) -> None:
        self.notices.append((kwargs["user_id"], kwargs["kind"], kwargs["text"]))

    @asynccontextmanager
    async def rendering(self, _target: ReplyTarget) -> AsyncIterator[None]:
        self.events.append("rendering_enter")
        try:
            yield
        finally:
            self.events.append("rendering_exit")


def rendered(
    data: bytes = b"ogg",
    *,
    queue: float = 2.417,
    render: float = 5.123,
) -> RenderedVoice:
    return RenderedVoice(
        VoiceAudio(data=data),
        queue_duration_seconds=queue,
        render_duration_seconds=render,
    )


@pytest.mark.parametrize(
    ("presentation", "outcome", "expected"),
    [
        (
            VoicePresentation(model_name="Qwen3-TTS", voice_name="aiden"),
            rendered(queue=2.417, render=5.123),
            "Qwen3-TTS (aiden) · render 5.123 s · queue 2.417 s",
        ),
        (
            VoicePresentation(model_name="Silero", voice_name="xenia"),
            rendered(queue=0.0, render=1.204),
            "Silero (xenia) · render 1.204 s · queue 0.000 s",
        ),
    ],
)
def test_voice_caption_uses_stable_exact_format(
    presentation: VoicePresentation,
    outcome: RenderedVoice,
    expected: str,
) -> None:
    assert presentation.caption(outcome) == expected


def as_message(message: FakeMessage) -> Message:
    return cast(Message, cast(Any, message))


def as_user(user: FakeUser) -> User:
    return cast(User, cast(Any, user))


def as_service(service: StubSpeechService) -> BotSpeechService:
    return cast(BotSpeechService, cast(Any, service))


def as_progress(progress: StubProgress) -> TelegramProgressCoordinator:
    return cast(TelegramProgressCoordinator, cast(Any, progress))


async def call_text(
    message: FakeMessage,
    service: StubSpeechService,
    progress: StubProgress | None = None,
    *,
    user: FakeUser | None = None,
) -> StubProgress:
    progress = progress or StubProgress()
    await handle_text(
        as_message(message),
        as_user(user or FakeUser()),
        as_service(service),
        as_progress(progress),
        PRESENTATION,
    )
    return progress


async def test_start_and_help_use_sender_locale() -> None:
    russian = FakeMessage()
    english = FakeMessage()

    await handle_start(as_message(russian), as_user(FakeUser(language_code="ru-RU")))
    await handle_help(as_message(english), as_user(FakeUser(language_code=None)))

    assert russian.answers == [message_text(Locale.RU, MessageKey.START)]
    assert english.answers == [message_text(Locale.EN, MessageKey.HELP)]


@pytest.mark.parametrize("forward_origin", [None, "visible-user", "privacy-hidden"])
async def test_successful_text_uses_queue_path_and_exact_caption(
    forward_origin: str | None,
) -> None:
    supplied_text = "  Точный текст без метаданных  "
    message = FakeMessage(text=supplied_text, forward_origin=forward_origin)
    service = StubSpeechService(StubJob(rendered()))

    progress = await call_text(message, service, user=FakeUser(id=88, language_code="ru"))

    assert service.calls == [(88, supplied_text)]
    assert progress.events == ["rendering_enter", "rendering_exit"]
    assert len(message.bot.voices) == 1
    chat_id, voice, caption, reply = message.bot.voices[0]
    assert chat_id == 42
    assert voice.data == b"ogg"
    assert caption == "Qwen3-TTS (aiden) · render 5.123 s · queue 2.417 s"
    assert reply == ReplyParameters(message_id=9)


async def test_queued_job_registers_one_backlog_until_start() -> None:
    message = FakeMessage(text="queued")
    service = StubSpeechService(StubJob(rendered(), backlog_id=11))

    progress = await call_text(message, service)

    assert progress.events == [
        "queue_enter:11",
        "queue_leave:11",
        "rendering_enter",
        "rendering_exit",
    ]


@pytest.mark.parametrize(
    ("reason", "key"),
    [
        (RejectionReason.USER_QUEUE_FULL, MessageKey.USER_QUEUE_FULL),
        (RejectionReason.GLOBAL_QUEUE_FULL, MessageKey.GLOBAL_QUEUE_FULL),
        (RejectionReason.SHUTTING_DOWN, MessageKey.RESTARTING),
    ],
)
async def test_submission_rejections_are_coalesced_and_localized(
    reason: RejectionReason,
    key: MessageKey,
) -> None:
    progress = await call_text(
        FakeMessage(text="hello"),
        StubSpeechService(RenderRejected(reason)),
    )

    assert progress.notices == [(42, reason.value, message_text(Locale.EN, key))]


@pytest.mark.parametrize(
    ("reason", "key"),
    [
        (AbortReason.EXPIRED, MessageKey.QUEUE_EXPIRED),
        (AbortReason.SHUTDOWN, MessageKey.RESTARTING),
    ],
)
async def test_waiting_abort_leaves_backlog_and_sends_notice(
    reason: AbortReason,
    key: MessageKey,
) -> None:
    aborted = RenderAborted(reason)
    progress = await call_text(
        FakeMessage(text="hello"),
        StubSpeechService(
            StubJob(aborted, backlog_id=3, start_abort=aborted),
        ),
    )

    assert progress.events == ["queue_enter:3", "queue_leave:3"]
    assert progress.notices == [(42, reason.value, message_text(Locale.EN, key))]


@pytest.mark.parametrize(
    ("text", "key"),
    [
        (" \n\t", MessageKey.EMPTY_TEXT),
        ("x" * (MAX_TELEGRAM_TEXT_LENGTH + 1), MessageKey.TEXT_TOO_LONG),
    ],
)
async def test_invalid_text_is_rejected_before_submission(text: str, key: MessageKey) -> None:
    message = FakeMessage(text=text)
    service = StubSpeechService(StubJob(rendered()))

    await call_text(message, service)

    assert service.calls == []
    assert message.replies == [message_text(Locale.EN, key)]


async def test_unsupported_content_without_text_gets_guidance() -> None:
    message = FakeMessage()

    await handle_unsupported(as_message(message), as_user(FakeUser(language_code="ru")))

    assert message.replies == [message_text(Locale.RU, MessageKey.UNSUPPORTED)]


async def test_private_and_text_filters_ignore_groups_and_accept_text_content() -> None:
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
    assert await TextMessageFilter()(private_caption)


@pytest.mark.parametrize(
    ("content", "expected_text"),
    [
        ({"text": "Прочитай это"}, "Прочитай это"),
        ({"caption": "Озвучь эту подпись"}, "Озвучь эту подпись"),
        (
            {
                "rich_message": {
                    "blocks": [
                        {
                            "type": "list",
                            "items": [
                                {
                                    "label": "•",
                                    "blocks": [
                                        {
                                            "type": "paragraph",
                                            "text": "Озвучь этот структурированный текст",
                                        }
                                    ],
                                }
                            ],
                        }
                    ]
                }
            },
            "Озвучь этот структурированный текст",
        ),
    ],
)
async def test_dispatcher_routes_real_private_message_model(
    monkeypatch: pytest.MonkeyPatch,
    content: dict[str, Any],
    expected_text: str,
) -> None:
    service = StubSpeechService(StubJob(rendered()))
    progress = StubProgress()
    dispatcher = create_dispatcher(
        as_service(service),
        HandlerActivity(),
        as_progress(progress),
        PRESENTATION,
    )
    sent_voices: list[tuple[int, str]] = []

    async def capture_voice(
        _bot: Bot,
        *,
        chat_id: int,
        voice: BufferedInputFile,
        caption: str,
        **_kwargs: Any,
    ) -> None:
        await asyncio.sleep(0)
        assert voice.data == b"ogg"
        sent_voices.append((chat_id, caption))

    monkeypatch.setattr(Bot, "send_voice", capture_voice)
    bot = Bot(token="123456:local-test-token")
    update = Update.model_validate(
        {
            "update_id": 1,
            "message": {
                "message_id": 10,
                "date": MESSAGE_DATE,
                "chat": {"id": 88, "type": ChatType.PRIVATE},
                "from": {
                    "id": 88,
                    "is_bot": False,
                    "first_name": "Test",
                    "language_code": "en",
                },
                **content,
            },
        },
        context={"bot": bot},
    )

    try:
        await dispatcher.feed_update(bot, update)
    finally:
        await bot.session.close()

    assert service.calls == [(88, expected_text)]
    assert sent_voices == [(88, "Qwen3-TTS (aiden) · render 5.123 s · queue 2.417 s")]


async def test_concurrent_dispatch_preserves_message_order_during_admission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = StubSpeechService(StubJob(rendered()))
    dispatcher = create_dispatcher(
        as_service(service),
        HandlerActivity(),
        as_progress(StubProgress()),
        PRESENTATION,
    )
    first_reached_filter = asyncio.Event()
    release_first = asyncio.Event()
    original_filter = TextMessageFilter.__call__

    async def delayed_first_filter(self: TextMessageFilter, message: Message) -> bool:
        if message.message_id == 10:
            first_reached_filter.set()
            await release_first.wait()
        return await original_filter(self, message)

    async def ignore_voice(_bot: Bot, **_kwargs: Any) -> None:
        await asyncio.sleep(0)

    monkeypatch.setattr(TextMessageFilter, "__call__", delayed_first_filter)
    monkeypatch.setattr(Bot, "send_voice", ignore_voice)
    bot = Bot(token="123456:local-test-token")

    def make_update(update_id: int, message_id: int, text: str) -> Update:
        return Update.model_validate(
            {
                "update_id": update_id,
                "message": {
                    "message_id": message_id,
                    "date": MESSAGE_DATE,
                    "chat": {"id": 88, "type": ChatType.PRIVATE},
                    "from": {
                        "id": 88,
                        "is_bot": False,
                        "first_name": "Test",
                        "language_code": "en",
                    },
                    "text": text,
                },
            },
            context={"bot": bot},
        )

    try:
        first = asyncio.create_task(dispatcher.feed_update(bot, make_update(1, 10, "first")))
        await first_reached_filter.wait()
        second = asyncio.create_task(dispatcher.feed_update(bot, make_update(2, 11, "second")))
        await asyncio.sleep(0)
        release_first.set()
        await asyncio.gather(first, second)
    finally:
        await bot.session.close()

    assert service.calls == [(88, "first"), (88, "second")]


async def test_render_failure_logs_only_safe_diagnostics(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret_text = "highly private source text"
    message = FakeMessage(text=secret_text)
    service = StubSpeechService(StubJob(RuntimeError(secret_text)))

    with caplog.at_level(logging.ERROR):
        await call_text(message, service)

    assert secret_text not in caplog.text
    assert "speech_render_failed exception_type=RuntimeError" in caplog.text
    assert message.bot.messages[0][1] == message_text(Locale.EN, MessageKey.RENDER_FAILED)


async def test_success_log_reports_both_durations_without_source_text(
    caplog: pytest.LogCaptureFixture,
) -> None:
    source_text = "private timing sentinel"
    with caplog.at_level(logging.INFO):
        await call_text(
            FakeMessage(text=source_text),
            StubSpeechService(StubJob(rendered(queue=1.25, render=3.5))),
        )

    assert "queue_duration_seconds=1.250" in caplog.text
    assert "render_duration_seconds=3.500" in caplog.text
    assert source_text not in caplog.text


async def test_upload_failure_is_not_retried_or_logged_with_content(
    caplog: pytest.LogCaptureFixture,
) -> None:
    source_text = "never put this in logs"
    message = FakeMessage(text=source_text, bot=FakeBot(send_error=RuntimeError(source_text)))

    with caplog.at_level(logging.ERROR):
        await call_text(message, StubSpeechService(StubJob(rendered())))

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
