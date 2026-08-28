from importlib.metadata import PackageNotFoundError, version

import pytest

import telegram_tts_bot


def test_package_is_installed() -> None:
    assert version("telegram-tts-bot") == "0.1.0"
    assert telegram_tts_bot.__doc__ == "Vslukh Telegram text-to-speech bot."


def test_accelerated_qwen_runtime_is_installed_without_conflicting_distribution() -> None:
    assert version("faster-qwen3-tts") == "0.4.0"
    assert version("qwen-tts-hf") == "0.1.1.post1"
    with pytest.raises(PackageNotFoundError):
        version("qwen-tts")
