from pathlib import Path

import pytest

from telegram_tts_bot.speech import factory
from telegram_tts_bot.speech.renderer import VoiceRenderer


@pytest.mark.parametrize("voice", ["kseniya", "xenia", "baya"])
def test_factory_verifies_encoder_and_loads_silero(
    monkeypatch: pytest.MonkeyPatch,
    voice: str,
) -> None:
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

    renderer = factory.create_voice_renderer(
        qwen_model_path=Path("qwen"),
        silero_model_path=Path("model.pt"),
        voice=voice,
        max_workers=2,
    )

    assert isinstance(renderer, VoiceRenderer)
    assert calls == ["ffmpeg", (Path("model.pt"), voice)]


@pytest.mark.parametrize("voice", ["aiden", "serena"])
def test_factory_loads_qwen_for_supported_voice(
    monkeypatch: pytest.MonkeyPatch, voice: str
) -> None:
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
    monkeypatch.setattr(factory, "QwenWaveSynthesizer", Synthesizer)

    renderer = factory.create_voice_renderer(
        qwen_model_path=Path("qwen"),
        silero_model_path=Path("silero.pt"),
        voice=voice,
        max_workers=1,
    )

    assert isinstance(renderer, VoiceRenderer)
    assert calls == ["ffmpeg", (Path("qwen"), voice)]
