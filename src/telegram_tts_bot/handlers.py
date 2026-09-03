"""Private-chat Telegram handlers for commands, text, and unsupported content."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from dataclasses import dataclass

from aiogram import Router
from aiogram.enums import ChatType, MessageEntityType
from aiogram.filters import Filter
from aiogram.types import BufferedInputFile, Message, ReplyParameters, User

from telegram_tts_bot.bot_service import (
    AbortReason,
    BotSpeechService,
    RejectionReason,
    RenderAborted,
    RenderedVoice,
    RenderRejected,
)
from telegram_tts_bot.localization import (
    Locale,
    MessageKey,
    locale_for_language_code,
    message_text,
)
from telegram_tts_bot.progress import ReplyTarget, TelegramProgressCoordinator

MAX_TELEGRAM_TEXT_LENGTH = 4096

_RICH_TEXT_FIELDS = frozenset({
    "alternative_text",
    "caption",
    "credit",
    "expression",
    "summary",
    "text",
})
_RICH_CONTAINER_FIELDS = frozenset({"blocks", "cells", "items"})

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class VoicePresentation:
    """Stable user-facing model and configured voice labels."""

    model_name: str
    voice_name: str

    def caption(self, rendered: RenderedVoice) -> str:
        """Format one plain-text Telegram voice caption."""
        return (
            f"{self.model_name} ({self.voice_name})"
            f" · render {rendered.render_duration_seconds:.3f} s"
            f" · queue {rendered.queue_duration_seconds:.3f} s"
        )


class PrivateChatFilter(Filter):
    """Select private messages without dispatching a sync filter to a worker thread."""

    async def __call__(self, message: Message) -> bool:
        return message.chat.type == ChatType.PRIVATE


class TextMessageFilter(Filter):
    """Select messages with text or a media caption."""

    async def __call__(self, message: Message) -> bool:
        return _text_to_speak(message) is not None


def _text_to_speak(message: Message) -> str | None:
    """Return Telegram's plain text representation of supported message content."""
    if message.text is not None:
        return message.text
    if message.caption is not None:
        return message.caption
    if message.rich_message is None:
        return None
    return _flatten_rich_value(message.rich_message.model_dump(exclude_none=True))


def _flatten_rich_value(value: object, *, sequence_separator: str = "\n") -> str | None:
    """Flatten human-visible rich-message fields without narrating metadata."""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        sequence_parts = [
            part
            for item in value
            if (part := _flatten_rich_value(item, sequence_separator=sequence_separator))
            is not None
        ]
        return sequence_separator.join(sequence_parts) if sequence_parts else None
    if not isinstance(value, Mapping):
        return None

    parts: list[str] = []
    for key, item in value.items():
        if key in _RICH_TEXT_FIELDS:
            part = _flatten_rich_value(item, sequence_separator="")
        elif key in _RICH_CONTAINER_FIELDS:
            part = _flatten_rich_value(item)
        else:
            continue
        if part is not None:
            parts.append(part)
    return "\n".join(parts) if parts else None


class _PlainCommandFilter(Filter):
    """Match only unformatted `/start` and `/help` commands."""

    def __init__(self, command: str):
        self._command = command

    async def __call__(self, message: Message) -> bool:
        text = message.text
        if text is None:
            return False
        if not text.startswith("/"):
            return False

        command_token = text.split(None, 1)[0]
        command_name = command_token[1:].split("@", 1)[0].lower()
        if command_name != self._command:
            return False

        entities = message.entities
        if not entities:
            return True
        if len(entities) != 1:
            return False

        command_entity = entities[0]
        return (
            command_entity.type == MessageEntityType.BOT_COMMAND
            and command_entity.offset == 0
            and command_entity.length == len(command_token)
        )


def create_router() -> Router:
    """Create the private-chat-only router in deterministic handler order."""
    router = Router(name=__name__)
    router.message.filter(PrivateChatFilter())
    router.message.register(handle_start, _PlainCommandFilter("start"))
    router.message.register(handle_help, _PlainCommandFilter("help"))
    router.message.register(handle_text, TextMessageFilter())
    router.message.register(handle_unsupported)
    return router


async def handle_start(message: Message, event_from_user: User) -> None:
    """Send the localized welcome message."""
    await _safe_answer(
        message,
        message_text(locale_for_language_code(event_from_user.language_code), MessageKey.START),
        response_kind="start",
    )


async def handle_help(message: Message, event_from_user: User) -> None:
    """Send detailed localized usage help."""
    await _safe_answer(
        message,
        message_text(locale_for_language_code(event_from_user.language_code), MessageKey.HELP),
        response_kind="help",
    )


async def handle_text(
    message: Message,
    event_from_user: User,
    speech_service: BotSpeechService,
    progress: TelegramProgressCoordinator,
    voice_presentation: VoicePresentation,
) -> None:
    """Submit supported private text through one bounded queue path."""
    text = _text_to_speak(message)
    if text is None:
        return
    locale = locale_for_language_code(event_from_user.language_code)
    if not text.strip():
        await _safe_reply(message, message_text(locale, MessageKey.EMPTY_TEXT), "empty_text")
        return
    if len(text) > MAX_TELEGRAM_TEXT_LENGTH:
        await _safe_reply(message, message_text(locale, MessageKey.TEXT_TOO_LONG), "text_too_long")
        return

    user_id = event_from_user.id
    characters = len(text)
    target = ReplyTarget(
        bot=message.bot,
        chat_id=message.chat.id,
        message_id=message.message_id,
    )
    del message, event_from_user

    submission = await speech_service.submit(user_id=user_id, text=text)
    del text
    if isinstance(submission, RenderRejected):
        await _reply_to_rejection(
            progress=progress,
            target=target,
            user_id=user_id,
            locale=locale,
            rejection=submission,
        )
        return

    job = submission
    backlog_id = job.backlog_id
    if backlog_id is not None:
        await progress.enter_backlog(
            user_id=user_id,
            backlog_id=backlog_id,
            target=target,
            text=message_text(locale, MessageKey.QUEUE_WAIT),
        )
    try:
        aborted = await job.wait_started()
    except asyncio.CancelledError:
        await speech_service.cancel(job)
        raise
    finally:
        if backlog_id is not None:
            await progress.leave_backlog(user_id=user_id, backlog_id=backlog_id)

    if aborted is not None:
        await _reply_to_abort(
            progress=progress,
            target=target,
            user_id=user_id,
            locale=locale,
            aborted=aborted,
        )
        return

    try:
        async with progress.rendering(target):
            outcome = await job.result()
    except asyncio.CancelledError:
        await speech_service.cancel(job)
        raise
    except Exception as error:
        logger.error(
            "speech_render_failed exception_type=%s characters=%d",
            type(error).__name__,
            characters,
        )
        await _safe_target_reply(
            target,
            message_text(locale, MessageKey.RENDER_FAILED),
            response_kind="render_failed",
        )
        return

    if isinstance(outcome, RenderAborted):
        await _reply_to_abort(
            progress=progress,
            target=target,
            user_id=user_id,
            locale=locale,
            aborted=outcome,
        )
        return

    logger.info(
        "speech_rendered characters=%d output_bytes=%d queue_duration_seconds=%.3f "
        "render_duration_seconds=%.3f",
        characters,
        len(outcome.audio.data),
        outcome.queue_duration_seconds,
        outcome.render_duration_seconds,
    )
    await _safe_send_voice(target, outcome, voice_presentation.caption(outcome))


async def handle_unsupported(message: Message, event_from_user: User) -> None:
    """Explain the textual-content contract for messages without text or captions."""
    locale = locale_for_language_code(event_from_user.language_code)
    await _safe_reply(message, message_text(locale, MessageKey.UNSUPPORTED), "unsupported")


async def _reply_to_rejection(
    *,
    progress: TelegramProgressCoordinator,
    target: ReplyTarget,
    user_id: int,
    locale: Locale,
    rejection: RenderRejected,
) -> None:
    if rejection.reason is RejectionReason.USER_QUEUE_FULL:
        key = MessageKey.USER_QUEUE_FULL
    elif rejection.reason is RejectionReason.GLOBAL_QUEUE_FULL:
        key = MessageKey.GLOBAL_QUEUE_FULL
    else:
        key = MessageKey.RESTARTING
    await progress.send_coalesced(
        user_id=user_id,
        kind=rejection.reason.value,
        target=target,
        text=message_text(locale, key),
    )


async def _reply_to_abort(
    *,
    progress: TelegramProgressCoordinator,
    target: ReplyTarget,
    user_id: int,
    locale: Locale,
    aborted: RenderAborted,
) -> None:
    key = (
        MessageKey.QUEUE_EXPIRED if aborted.reason is AbortReason.EXPIRED else MessageKey.RESTARTING
    )
    await progress.send_coalesced(
        user_id=user_id,
        kind=aborted.reason.value,
        target=target,
        text=message_text(locale, key),
    )


async def _safe_send_voice(
    target: ReplyTarget,
    rendered: RenderedVoice,
    caption: str,
) -> None:
    bot = target.bot
    if bot is None:
        logger.error("voice_upload_failed exception_type=BotUnbound")
        return
    voice = BufferedInputFile(rendered.audio.data, filename=rendered.audio.filename)
    try:
        await bot.send_voice(
            chat_id=target.chat_id,
            voice=voice,
            caption=caption,
            parse_mode=None,
            reply_parameters=ReplyParameters(message_id=target.message_id),
        )
    except Exception as error:
        logger.error(
            "voice_upload_failed exception_type=%s output_bytes=%d",
            type(error).__name__,
            len(rendered.audio.data),
        )


async def _safe_target_reply(
    target: ReplyTarget,
    text: str,
    *,
    response_kind: str,
) -> None:
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
        _log_text_send_failure(error, response_kind)


async def _safe_answer(message: Message, text: str, *, response_kind: str) -> None:
    try:
        await message.answer(text)
    except Exception as error:
        _log_text_send_failure(error, response_kind)


async def _safe_reply(message: Message, text: str, response_kind: str) -> None:
    try:
        await message.reply(text)
    except Exception as error:
        _log_text_send_failure(error, response_kind)


def _log_text_send_failure(error: Exception, response_kind: str) -> None:
    logger.error(
        "text_response_failed response_kind=%s exception_type=%s",
        response_kind,
        type(error).__name__,
    )
