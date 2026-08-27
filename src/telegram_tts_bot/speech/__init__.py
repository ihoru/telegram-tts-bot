"""Engine-neutral speech rendering API."""

from telegram_tts_bot.speech.errors import (
    EncodingError,
    InvalidTextError,
    SynthesisError,
    VoiceRenderError,
)
from telegram_tts_bot.speech.factory import create_voice_renderer
from telegram_tts_bot.speech.renderer import VoiceRenderer
from telegram_tts_bot.speech.types import VoiceAudio, WavAudio, WaveSynthesizer

__all__ = [
    "EncodingError",
    "InvalidTextError",
    "SynthesisError",
    "VoiceAudio",
    "VoiceRenderError",
    "VoiceRenderer",
    "WavAudio",
    "WaveSynthesizer",
    "create_voice_renderer",
]
