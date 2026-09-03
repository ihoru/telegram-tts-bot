"""Private-chat Telegram handlers for commands, text, and unsupported content."""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping

from aiogram import Router
from aiogram.enums import ChatAction, ChatType
from aiogram.filters import Command, CommandStart, Filter
from aiogram.types import BufferedInputFile, Message, User

from telegram_tts_bot.bot_service import (
    BotSpeechService,
    RejectionReason,
    RenderRejected,
)
from telegram_tts_bot.localization import (
    MessageKey,
    locale_for_language_code,
    message_text,
)

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


def create_router() -> Router:
    """Create the private-chat-only router in deterministic handler order."""
    router = Router(name=__name__)
    router.message.filter(PrivateChatFilter())
    router.message.register(handle_start, CommandStart())
    router.message.register(handle_help, Command("help"))
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
) -> None:
    """Render direct, copied, forwarded, and caption text through the same path."""
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

    await _safe_record_voice_action(message)
    render_started = time.perf_counter()
    try:
        result = await speech_service.try_render(user_id=event_from_user.id, text=text)
    except Exception as error:
        logger.error(
            "speech_render_failed exception_type=%s characters=%d",
            type(error).__name__,
            len(text),
        )
        await _safe_reply(message, message_text(locale, MessageKey.RENDER_FAILED), "render_failed")
        return

    if isinstance(result, RenderRejected):
        key = (
            MessageKey.USER_BUSY
            if result.reason is RejectionReason.USER_CAPACITY
            else MessageKey.GLOBAL_BUSY
        )
        await _safe_reply(message, message_text(locale, key), result.reason.value)
        return

    render_duration_seconds = time.perf_counter() - render_started
    logger.info(
        "speech_rendered characters=%d output_bytes=%d render_duration_seconds=%.3f",
        len(text),
        len(result.audio.data),
        render_duration_seconds,
    )
    voice = BufferedInputFile(result.audio.data, filename=result.audio.filename)
    try:
        await message.reply_voice(voice)
    except Exception as error:
        logger.error(
            "voice_upload_failed exception_type=%s output_bytes=%d",
            type(error).__name__,
            len(result.audio.data),
        )


async def handle_unsupported(message: Message, event_from_user: User) -> None:
    """Explain the textual-content contract for messages without text or captions."""
    locale = locale_for_language_code(event_from_user.language_code)
    await _safe_reply(message, message_text(locale, MessageKey.UNSUPPORTED), "unsupported")


async def _safe_record_voice_action(message: Message) -> None:
    bot = message.bot
    if bot is None:
        logger.warning("chat_action_skipped action=record_voice reason=bot_unbound")
        return
    try:
        await bot.send_chat_action(
            chat_id=message.chat.id,
            action=ChatAction.RECORD_VOICE,
        )
    except Exception as error:
        logger.warning(
            "chat_action_failed action=record_voice exception_type=%s",
            type(error).__name__,
        )


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
