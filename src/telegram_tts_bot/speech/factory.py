"""Production speech composition."""

from pathlib import Path

from telegram_tts_bot.speech.encoding import FfmpegVoiceEncoder
from telegram_tts_bot.speech.renderer import VoiceRenderer
from telegram_tts_bot.speech.silero import SileroWaveSynthesizer


def create_voice_renderer(
    model_path: Path,
    speaker: str,
    max_workers: int,
) -> VoiceRenderer:
    """Build the production renderer and verify dependencies up front."""
    encoder = FfmpegVoiceEncoder()
    encoder.verify_available()
    synthesizer = SileroWaveSynthesizer.load(model_path, speaker)
    return VoiceRenderer(synthesizer, encoder, max_workers=max_workers)
