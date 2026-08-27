from pathlib import Path

import pytest

from telegram_tts_bot.speech import factory
from telegram_tts_bot.speech.renderer import VoiceRenderer


def test_factory_verifies_encoder_and_loads_piper(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[object] = []

    class Encoder:
        def verify_available(self) -> None:
            calls.append("ffmpeg")

        def encode(self, audio: object) -> object:
            return audio

    class Synthesizer:
        @classmethod
        def load(cls, model: Path, config: Path) -> object:
            calls.append((model, config))
            return object()

    monkeypatch.setattr(factory, "FfmpegVoiceEncoder", Encoder)
    monkeypatch.setattr(factory, "PiperWaveSynthesizer", Synthesizer)

    renderer = factory.create_voice_renderer(Path("model"), Path("config"), 2)

    assert isinstance(renderer, VoiceRenderer)
    assert calls == ["ffmpeg", (Path("model"), Path("config"))]
