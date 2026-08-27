"""Production speech composition."""

from pathlib import Path

from telegram_tts_bot.speech.encoding import FfmpegVoiceEncoder
from telegram_tts_bot.speech.piper import PiperWaveSynthesizer
from telegram_tts_bot.speech.renderer import VoiceRenderer


def create_voice_renderer(
    model_path: Path,
    config_path: Path,
    max_workers: int,
) -> VoiceRenderer:
    """Build the single v1 renderer and verify dependencies up front."""
    encoder = FfmpegVoiceEncoder()
    encoder.verify_available()
    synthesizer = PiperWaveSynthesizer.load(model_path, config_path)
    return VoiceRenderer(synthesizer, encoder, max_workers=max_workers)
