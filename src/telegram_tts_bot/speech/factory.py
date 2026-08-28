"""Production speech composition."""

from pathlib import Path

from telegram_tts_bot.speech.encoding import FfmpegVoiceEncoder
from telegram_tts_bot.speech.qwen import QwenWaveSynthesizer
from telegram_tts_bot.speech.renderer import VoiceRenderer
from telegram_tts_bot.speech.silero import SileroWaveSynthesizer
from telegram_tts_bot.speech.types import WaveSynthesizer


def create_voice_renderer(
    qwen_model_path: Path,
    silero_model_path: Path,
    voice: str,
    max_workers: int,
) -> VoiceRenderer:
    """Build the production renderer and verify dependencies up front."""
    encoder = FfmpegVoiceEncoder()
    encoder.verify_available()
    synthesizer: WaveSynthesizer
    if voice in {"aiden", "serena"}:
        synthesizer = QwenWaveSynthesizer.load(qwen_model_path, voice)
    else:
        synthesizer = SileroWaveSynthesizer.load(silero_model_path, voice)
    return VoiceRenderer(synthesizer, encoder, max_workers=max_workers)
