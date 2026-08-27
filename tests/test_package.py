from importlib.metadata import version

import telegram_tts_bot


def test_package_is_installed() -> None:
    assert version("telegram-tts-bot") == "0.1.0"
    assert telegram_tts_bot.__doc__ == "Vslukh Telegram text-to-speech bot."
