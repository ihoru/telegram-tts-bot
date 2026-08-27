"""Immutable process-environment configuration for the bot runtime."""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MODEL_PATH = Path(".models/piper/ru_RU-denis-medium.onnx")
DEFAULT_CONFIG_PATH = Path(".models/piper/ru_RU-denis-medium.onnx.json")


class ConfigurationError(ValueError):
    """Raised when process configuration is missing or invalid."""


@dataclass(frozen=True, slots=True)
class BotSettings:
    """Validated settings that cannot change after startup."""

    telegram_bot_token: str
    piper_model_path: Path = DEFAULT_MODEL_PATH
    piper_config_path: Path = DEFAULT_CONFIG_PATH
    max_concurrency: int = 5
    max_concurrency_per_user: int = 1
    log_level: int = logging.INFO

    @classmethod
    def from_environment(cls, environment: Mapping[str, str] | None = None) -> BotSettings:
        """Build settings from an explicit mapping or the process environment."""
        values = os.environ if environment is None else environment
        token = values.get("TELEGRAM_BOT_TOKEN", "")
        _validate_token(token)

        max_concurrency = _positive_integer(values, "TTS_MAX_CONCURRENCY", default=5)
        per_user = _positive_integer(values, "TTS_MAX_CONCURRENCY_PER_USER", default=1)
        if per_user > max_concurrency:
            raise ConfigurationError(
                "TTS_MAX_CONCURRENCY_PER_USER must not exceed TTS_MAX_CONCURRENCY"
            )

        return cls(
            telegram_bot_token=token,
            piper_model_path=Path(
                values.get("PIPER_MODEL_PATH", str(DEFAULT_MODEL_PATH))
            ).expanduser(),
            piper_config_path=Path(
                values.get("PIPER_CONFIG_PATH", str(DEFAULT_CONFIG_PATH))
            ).expanduser(),
            max_concurrency=max_concurrency,
            max_concurrency_per_user=per_user,
            log_level=_logging_level(values.get("LOG_LEVEL", "INFO")),
        )


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
