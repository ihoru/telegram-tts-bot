from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from telegram_tts_bot.config import BotSettings, ConfigurationError
from telegram_tts_bot.localization import Locale, MessageKey, locale_for_language_code, message_text

VALID_TOKEN = "123456:local-test-token"


def test_settings_use_documented_defaults() -> None:
    settings = BotSettings.from_environment({"TELEGRAM_BOT_TOKEN": VALID_TOKEN})

    assert settings.telegram_bot_token == VALID_TOKEN
    assert settings.piper_model_path == Path(".models/piper/ru_RU-denis-medium.onnx")
    assert settings.piper_config_path == Path(".models/piper/ru_RU-denis-medium.onnx.json")
    assert settings.max_concurrency == 5
    assert settings.max_concurrency_per_user == 1
    assert settings.log_level == 20


def test_settings_accept_safe_overrides() -> None:
    settings = BotSettings.from_environment({
        "TELEGRAM_BOT_TOKEN": VALID_TOKEN,
        "PIPER_MODEL_PATH": "/models/voice.onnx",
        "PIPER_CONFIG_PATH": "/models/voice.onnx.json",
        "TTS_MAX_CONCURRENCY": "8",
        "TTS_MAX_CONCURRENCY_PER_USER": "2",
        "LOG_LEVEL": "warning",
    })

    assert settings.piper_model_path == Path("/models/voice.onnx")
    assert settings.piper_config_path == Path("/models/voice.onnx.json")
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


@pytest.mark.parametrize("language_code", ["ru", "RU", "ru-RU", "ru_ua"])
def test_russian_locale_is_selected_for_ru_prefix(language_code: str) -> None:
    assert locale_for_language_code(language_code) is Locale.RU


@pytest.mark.parametrize("language_code", [None, "", "en", "uk", "fr"])
def test_english_locale_is_the_fallback(language_code: str | None) -> None:
    assert locale_for_language_code(language_code) is Locale.EN


def test_start_and_help_copy_match_the_accepted_profile() -> None:
    assert message_text(Locale.RU, MessageKey.START).startswith('Привет! Я "Вслух"')
    assert message_text(Locale.EN, MessageKey.START).startswith("Hello! I am Vslukh")
    assert "данных пересылки" in message_text(Locale.RU, MessageKey.HELP)
    assert "forwarding details" in message_text(Locale.EN, MessageKey.HELP)
