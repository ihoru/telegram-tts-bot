"""Immutable process-environment configuration for the bot runtime."""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

DEFAULT_SILERO_MODEL_PATH = Path(".models/silero/v5_5_ru.pt")
DEFAULT_QWEN_MODEL_PATH = Path(".models/qwen3-tts-12hz-0.6b-customvoice")
DEFAULT_TTS_VOICE = "aiden"
DEFAULT_MAX_QUEUE_SIZE = 20
DEFAULT_MAX_QUEUE_SIZE_PER_USER = 10
DEFAULT_MAX_QUEUE_WAIT_SECONDS = 600
QWEN_TTS_VOICES = ("aiden", "serena")
SUPPORTED_TTS_VOICES = (*QWEN_TTS_VOICES, "kseniya", "xenia", "baya")


class ConfigurationError(ValueError):
    """Raised when process configuration is missing or invalid."""


@dataclass(frozen=True, slots=True)
class BotSettings:
    """Validated settings that cannot change after startup."""

    telegram_bot_token: str
    qwen_model_path: Path = DEFAULT_QWEN_MODEL_PATH
    silero_model_path: Path = DEFAULT_SILERO_MODEL_PATH
    tts_voice: str = DEFAULT_TTS_VOICE
    max_concurrency: int = 1
    max_concurrency_per_user: int = 1
    max_queue_size: int = DEFAULT_MAX_QUEUE_SIZE
    max_queue_size_per_user: int = DEFAULT_MAX_QUEUE_SIZE_PER_USER
    max_queue_wait_seconds: int = DEFAULT_MAX_QUEUE_WAIT_SECONDS
    log_level: int = logging.INFO

    @classmethod
    def from_environment(cls, environment: Mapping[str, str] | None = None) -> BotSettings:
        """Build settings from an explicit mapping or the process environment."""
        values = os.environ if environment is None else environment
        token = values.get("TELEGRAM_BOT_TOKEN", "")
        _validate_token(token)

        voice = validate_tts_voice(values.get("TTS_VOICE", DEFAULT_TTS_VOICE))
        max_concurrency = _positive_integer(values, "TTS_MAX_CONCURRENCY", default=1)
        per_user = _positive_integer(values, "TTS_MAX_CONCURRENCY_PER_USER", default=1)
        max_queue_size = _positive_integer(
            values,
            "TTS_MAX_QUEUE_SIZE",
            default=DEFAULT_MAX_QUEUE_SIZE,
        )
        max_queue_size_per_user = _positive_integer(
            values,
            "TTS_MAX_QUEUE_SIZE_PER_USER",
            default=DEFAULT_MAX_QUEUE_SIZE_PER_USER,
        )
        max_queue_wait_seconds = _positive_integer(
            values,
            "TTS_MAX_QUEUE_WAIT_SECONDS",
            default=DEFAULT_MAX_QUEUE_WAIT_SECONDS,
        )
        if voice in QWEN_TTS_VOICES and max_concurrency != 1:
            raise ConfigurationError("TTS_MAX_CONCURRENCY must be 1 when TTS_VOICE uses Qwen")
        if per_user > max_concurrency:
            raise ConfigurationError(
                "TTS_MAX_CONCURRENCY_PER_USER must not exceed TTS_MAX_CONCURRENCY"
            )
        if max_queue_size_per_user > max_queue_size:
            raise ConfigurationError(
                "TTS_MAX_QUEUE_SIZE_PER_USER must not exceed TTS_MAX_QUEUE_SIZE"
            )

        return cls(
            telegram_bot_token=token,
            qwen_model_path=Path(
                values.get("QWEN_MODEL_PATH", str(DEFAULT_QWEN_MODEL_PATH))
            ).expanduser(),
            silero_model_path=Path(
                values.get("SILERO_MODEL_PATH", str(DEFAULT_SILERO_MODEL_PATH))
            ).expanduser(),
            tts_voice=voice,
            max_concurrency=max_concurrency,
            max_concurrency_per_user=per_user,
            max_queue_size=max_queue_size,
            max_queue_size_per_user=max_queue_size_per_user,
            max_queue_wait_seconds=max_queue_wait_seconds,
            log_level=_logging_level(values.get("LOG_LEVEL", "INFO")),
        )


def validate_tts_voice(value: str) -> str:
    """Return one exact supported speaker identifier or reject the setting."""
    if value not in SUPPORTED_TTS_VOICES:
        choices = ", ".join(SUPPORTED_TTS_VOICES)
        raise ConfigurationError(f"TTS_VOICE must be one of: {choices}")
    return value


def model_name_for_voice(voice: str) -> str:
    """Return the stable caption label for one validated voice."""
    return "Qwen3-TTS" if voice in QWEN_TTS_VOICES else "Silero"


def _validate_token(token: str) -> None:
    if not token:
        raise ConfigurationError("TELEGRAM_BOT_TOKEN is required")
    left, separator, right = token.partition(":")
    if any(character.isspace() for character in token) or not separator:
        raise ConfigurationError("TELEGRAM_BOT_TOKEN is invalid")
    if not left.isdigit() or not right:
        raise ConfigurationError("TELEGRAM_BOT_TOKEN is invalid")


def _positive_integer(values: Mapping[str, str], name: str, *, default: int) -> int:
    raw_value = values.get(name, str(default))
    try:
        value = int(raw_value)
    except ValueError as error:
        raise ConfigurationError(f"{name} must be a positive integer") from error
    if value <= 0:
        raise ConfigurationError(f"{name} must be a positive integer")
    return value


def _logging_level(value: str) -> int:
    level = logging.getLevelNamesMapping().get(value.upper())
    if level is None:
        raise ConfigurationError("LOG_LEVEL must be a standard logging level name")
    return level
