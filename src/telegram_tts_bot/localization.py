"""Russian and English user-facing bot messages."""

from __future__ import annotations

from enum import StrEnum
from types import MappingProxyType
from typing import Final

_PRIVACY_POLICY_URL: Final = "http://telegram-tts-bot.iho.su/"
_RU_PRIVACY_POLICY_LINE: Final = f"Политика конфиденциальности: {_PRIVACY_POLICY_URL}"
_EN_PRIVACY_POLICY_LINE: Final = f"Privacy policy: {_PRIVACY_POLICY_URL}"


class Locale(StrEnum):
    """Locales supported by the bot interface."""

    EN = "en"
    RU = "ru"


class MessageKey(StrEnum):
    """Stable identifiers for user-visible messages."""

    START = "start"
    HELP = "help"
    GLOBAL_BUSY = "global_busy"
    USER_BUSY = "user_busy"
    GLOBAL_QUEUE_FULL = "global_queue_full"
    USER_QUEUE_FULL = "user_queue_full"
    QUEUE_WAIT = "queue_wait"
    QUEUE_EXPIRED = "queue_expired"
    RESTARTING = "restarting"
    UNSUPPORTED = "unsupported"
    EMPTY_TEXT = "empty_text"
    TEXT_TOO_LONG = "text_too_long"
    RENDER_FAILED = "render_failed"


_RU_MESSAGES: Final = MappingProxyType({
    MessageKey.START: (
        "Привет! Это Read Aloud.\n\n"
        "Я превращаю обычные и пересланные текстовые сообщения в голосовые заметки. "
        "В зависимости от настроенного голоса бот также может естественно читать "  # ruff: ignore[ambiguous-unicode-character-string]
        "английские слова и фразы.\n\n"
        "Отправьте мне текст или перешлите текстовое сообщение — я отвечу готовой "
        "голосовой заметкой.\n\n"
        "Озвучивание выполняется локально. Я не сохраняю сообщения и созданное аудио.\n\n"
        "/help — подробная справка\n\n" + _RU_PRIVACY_POLICY_LINE
    ),
    MessageKey.HELP: (
        "Как пользоваться:\n\n"
        "• Отправьте обычное текстовое сообщение.\n"
        "• Или перешлите текстовое сообщение из другого чата.\n"
        "• Получите голосовую заметку в ответ.\n\n"
        "Бот работает только в личном чате. Лучше всего он работает с русским текстом; "  # ruff: ignore[ambiguous-unicode-character-string]
        "качество английских слов и фраз зависит от настроенного голоса. "
        "Озвучивается только текст сообщения, без имени автора и данных пересылки. "
        "Сообщения и готовое аудио не сохраняются. Если бот занят, запросы ожидают "
        "в ограниченной очереди.\n\n"
        "/start — показать приветствие\n"
        "/help — показать эту справку\n\n" + _RU_PRIVACY_POLICY_LINE
    ),
    MessageKey.GLOBAL_BUSY: ("Сейчас все голоса заняты. Попробуйте ещё раз чуть позже."),
    MessageKey.USER_BUSY: (
        "Предыдущее сообщение ещё озвучивается. Дождитесь ответа и попробуйте снова."
    ),
    MessageKey.GLOBAL_QUEUE_FULL: (
        "Общая очередь заполнена. Попробуйте отправить сообщение немного позже."
    ),
    MessageKey.USER_QUEUE_FULL: (
        "В вашей очереди уже слишком много сообщений. Дождитесь начала озвучивания "  # ruff: ignore[ambiguous-unicode-character-string]
        "одного из них и попробуйте снова."
    ),
    MessageKey.QUEUE_WAIT: (
        "Ваши сообщения ожидают в очереди. Пожалуйста, подождите: озвучивание начнётся "
        "при первой возможности."
    ),
    MessageKey.QUEUE_EXPIRED: (
        "Некоторые сообщения слишком долго ожидали в очереди и были отменены. "
        "Пожалуйста, отправьте их снова."
    ),
    MessageKey.RESTARTING: (
        "Бот перезапускается, поэтому сообщения в очереди были отменены. "
        "Пожалуйста, отправьте их снова немного позже."
    ),
    MessageKey.UNSUPPORTED: (
        "Отправьте обычный текст или перешлите текстовое сообщение — я отвечу голосовой заметкой."
    ),
    MessageKey.EMPTY_TEXT: "Сообщение должно содержать текст.",
    MessageKey.TEXT_TOO_LONG: "Текст слишком длинный. Максимум — 4096 символов.",
    MessageKey.RENDER_FAILED: (
        "Не удалось озвучить сообщение. Попробуйте снова чуть позже."  # ruff: ignore[ambiguous-unicode-character-string]
    ),
})

_EN_MESSAGES: Final = MappingProxyType({
    MessageKey.START: (
        "Hi! This is Read Aloud.\n\n"
        "I turn regular and forwarded text messages into voice notes. Depending on "
        "the configured voice, the bot can also read English words and phrases "
        "naturally.\n\n"
        "Send me text or forward a text message, and I will reply with a ready-to-play "
        "voice note.\n\n"
        "Speech is generated locally. I do not store messages or generated audio.\n\n"
        "/help — detailed help\n\n" + _EN_PRIVACY_POLICY_LINE
    ),
    MessageKey.HELP: (
        "How to use the bot:\n\n"
        "• Send a regular text message.\n"
        "• Or forward a text message from another chat.\n"
        "• Receive a voice note in reply.\n\n"
        "The bot works only in private chats. It is strongest in Russian; the quality "
        "of English words and phrases depends on the configured voice. "
        "It reads only the message text, not the author name or forwarding details. "
        "Messages and generated audio are not stored. If the bot is busy, requests "
        "wait in a bounded queue.\n\n"
        "/start — show the welcome message\n"
        "/help — show this help\n\n" + _EN_PRIVACY_POLICY_LINE
    ),
    MessageKey.GLOBAL_BUSY: ("All voices are busy right now. Please try again a little later."),
    MessageKey.USER_BUSY: (
        "Your previous message is still being voiced. Wait for the reply and try again."
    ),
    MessageKey.GLOBAL_QUEUE_FULL: (
        "The shared queue is full. Please try sending the message again a little later."
    ),
    MessageKey.USER_QUEUE_FULL: (
        "You already have too many messages waiting. Wait for one to start and try again."
    ),
    MessageKey.QUEUE_WAIT: (
        "Your messages are waiting in the queue. Please wait; rendering will start "
        "as soon as possible."
    ),
    MessageKey.QUEUE_EXPIRED: (
        "Some messages waited in the queue too long and were cancelled. Please send them again."
    ),
    MessageKey.RESTARTING: (
        "The bot is restarting, so queued messages were cancelled. Please send them "
        "again in a little while."
    ),
    MessageKey.UNSUPPORTED: (
        "Send a regular text message or forward a text message and I will reply with a voice note."
    ),
    MessageKey.EMPTY_TEXT: "The message must contain text.",
    MessageKey.TEXT_TOO_LONG: "The text is too long. The maximum is 4,096 characters.",
    MessageKey.RENDER_FAILED: ("I could not voice this message. Please try again a little later."),
})

_MESSAGES: Final = MappingProxyType({Locale.RU: _RU_MESSAGES, Locale.EN: _EN_MESSAGES})


def locale_for_language_code(language_code: str | None) -> Locale:
    """Use Russian for ``ru*`` Telegram language codes and English otherwise."""
    if language_code is not None and language_code.casefold().startswith("ru"):
        return Locale.RU
    return Locale.EN


def message_text(locale: Locale, key: MessageKey) -> str:
    """Return localized copy for a stable message key."""
    return _MESSAGES[locale][key]
