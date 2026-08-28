from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from telegram_tts_bot.config import BotSettings, ConfigurationError
from telegram_tts_bot.localization import Locale, MessageKey, locale_for_language_code, message_text

VALID_TOKEN = "123456:local-test-token"


def test_settings_use_documented_defaults() -> None:
    settings = BotSettings.from_environment({"TELEGRAM_BOT_TOKEN": VALID_TOKEN})

    assert settings.telegram_bot_token == VALID_TOKEN
    assert settings.qwen_model_path == Path(".models/qwen3-tts-12hz-0.6b-customvoice")
    assert settings.silero_model_path == Path(".models/silero/v5_5_ru.pt")
    assert settings.tts_voice == "aiden"
    assert settings.max_concurrency == 1
    assert settings.max_concurrency_per_user == 1
    assert settings.log_level == 20


def test_settings_accept_safe_overrides() -> None:
    settings = BotSettings.from_environment({
        "TELEGRAM_BOT_TOKEN": VALID_TOKEN,
        "QWEN_MODEL_PATH": "~/models/qwen",
        "SILERO_MODEL_PATH": "~/models/voice.pt",
        "TTS_VOICE": "baya",
        "TTS_MAX_CONCURRENCY": "8",
        "TTS_MAX_CONCURRENCY_PER_USER": "2",
        "LOG_LEVEL": "warning",
    })

    assert settings.silero_model_path == Path("~/models/voice.pt").expanduser()
    assert settings.qwen_model_path == Path("~/models/qwen").expanduser()
    assert settings.tts_voice == "baya"
    assert settings.max_concurrency == 8
    assert settings.max_concurrency_per_user == 2
    assert settings.log_level == 30


@pytest.mark.parametrize(
    ("environment", "message"),
    [
        ({}, "TELEGRAM_BOT_TOKEN is required"),
        ({"TELEGRAM_BOT_TOKEN": "not-a-token"}, "TELEGRAM_BOT_TOKEN is invalid"),
        ({"TELEGRAM_BOT_TOKEN": "name:value"}, "TELEGRAM_BOT_TOKEN is invalid"),
        (
            {"TELEGRAM_BOT_TOKEN": VALID_TOKEN, "TTS_MAX_CONCURRENCY": "0"},
            "TTS_MAX_CONCURRENCY must be a positive integer",
        ),
        (
            {"TELEGRAM_BOT_TOKEN": VALID_TOKEN, "TTS_MAX_CONCURRENCY": "many"},
            "TTS_MAX_CONCURRENCY must be a positive integer",
        ),
        (
            {
                "TELEGRAM_BOT_TOKEN": VALID_TOKEN,
                "TTS_MAX_CONCURRENCY": "1",
                "TTS_MAX_CONCURRENCY_PER_USER": "2",
            },
            "TTS_MAX_CONCURRENCY_PER_USER must not exceed TTS_MAX_CONCURRENCY",
        ),
        (
            {"TELEGRAM_BOT_TOKEN": VALID_TOKEN, "LOG_LEVEL": "verbose"},
            "LOG_LEVEL must be a standard logging level name",
        ),
        (
            {"TELEGRAM_BOT_TOKEN": VALID_TOKEN, "TTS_VOICE": "denis"},
            "TTS_VOICE must be one of: aiden, serena, kseniya, xenia, baya",
        ),
        (
            {
                "TELEGRAM_BOT_TOKEN": VALID_TOKEN,
                "TTS_VOICE": "aiden",
                "TTS_MAX_CONCURRENCY": "2",
            },
            "TTS_MAX_CONCURRENCY must be 1 when TTS_VOICE uses Qwen",
        ),
    ],
)
def test_invalid_settings_are_secret_safe(
    environment: dict[str, str],
    message: str,
) -> None:
    with pytest.raises(ConfigurationError, match=message) as caught:
        BotSettings.from_environment(environment)

    assert VALID_TOKEN not in str(caught.value)


def test_settings_are_immutable() -> None:
    settings = BotSettings.from_environment({"TELEGRAM_BOT_TOKEN": VALID_TOKEN})

    with pytest.raises(FrozenInstanceError):
        settings.max_concurrency = 10  # type: ignore[misc]


@pytest.mark.parametrize("voice", ["aiden", "serena", "kseniya", "xenia", "baya"])
def test_settings_accept_every_supported_voice(voice: str) -> None:
    settings = BotSettings.from_environment({
        "TELEGRAM_BOT_TOKEN": VALID_TOKEN,
        "TTS_VOICE": voice,
        "TTS_MAX_CONCURRENCY": "1",
    })

    assert settings.tts_voice == voice


@pytest.mark.parametrize("language_code", ["ru", "RU", "ru-RU", "ru_ua"])
def test_russian_locale_is_selected_for_ru_prefix(language_code: str) -> None:
    assert locale_for_language_code(language_code) is Locale.RU


@pytest.mark.parametrize("language_code", [None, "", "en", "uk", "fr"])
def test_english_locale_is_the_fallback(language_code: str | None) -> None:
    assert locale_for_language_code(language_code) is Locale.EN


def test_start_and_help_copy_match_the_accepted_profile() -> None:
    assert message_text(Locale.RU, MessageKey.START) == (
        'Привет! Я "Вслух".\n\n'
        "Я превращаю обычные и пересланные текстовые сообщения в голосовые заметки. "
        "В зависимости от настроенного голоса бот также может естественно читать "  # ruff: ignore[ambiguous-unicode-character-string]
        "английские слова и фразы.\n\n"
        "Отправьте мне текст или перешлите текстовое сообщение — я отвечу готовой "
        "голосовой заметкой.\n\n"
        "Озвучивание выполняется локально. Я не сохраняю сообщения и созданное аудио.\n\n"
        "/help — подробная справка"
    )
    assert message_text(Locale.EN, MessageKey.START) == (
        "Hello! I am Vslukh.\n\n"
        "I turn regular and forwarded text messages into voice notes. Depending on "
        "the configured voice, the bot can also read English words and phrases "
        "naturally.\n\n"
        "Send me text or forward a text message, and I will reply with a ready-to-play "
        "voice note.\n\n"
        "Speech is generated locally. I do not store messages or generated audio.\n\n"
        "/help — detailed help"
    )
    assert "данных пересылки" in message_text(Locale.RU, MessageKey.HELP)
    assert "forwarding details" in message_text(Locale.EN, MessageKey.HELP)
