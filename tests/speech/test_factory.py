from pathlib import Path

import pytest

from telegram_tts_bot.speech import factory
from telegram_tts_bot.speech.renderer import VoiceRenderer


def test_factory_verifies_encoder_and_loads_silero(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[object] = []

    class Encoder:
        def verify_available(self) -> None:
            calls.append("ffmpeg")

        def encode(self, audio: object) -> object:
            return audio

    class Synthesizer:
        @classmethod
        def load(cls, model: Path, speaker: str) -> object:
            calls.append((model, speaker))
            return object()

    monkeypatch.setattr(factory, "FfmpegVoiceEncoder", Encoder)
    monkeypatch.setattr(factory, "SileroWaveSynthesizer", Synthesizer)

    renderer = factory.create_voice_renderer(Path("model.pt"), "baya", 2)

    assert isinstance(renderer, VoiceRenderer)
    assert calls == ["ffmpeg", (Path("model.pt"), "baya")]
