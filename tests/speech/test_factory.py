import subprocess
import sys
from pathlib import Path

import pytest

from telegram_tts_bot.speech import factory, qwen
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
    monkeypatch.setattr(qwen, "QwenWaveSynthesizer", Synthesizer)

    renderer = factory.create_voice_renderer(
        qwen_model_path=Path("qwen"),
        silero_model_path=Path("silero.pt"),
        voice=voice,
        max_workers=1,
    )

    assert isinstance(renderer, VoiceRenderer)
    assert calls == ["ffmpeg", (Path("qwen"), voice)]


@pytest.mark.parametrize("voice", ["aiden", "serena"])
def test_startup_imports_without_qwen_and_selection_fails_clearly(voice: str) -> None:
    # A fresh interpreter prevents earlier Qwen unit tests from hiding eager imports.
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import importlib.abc
import sys
from pathlib import Path

class BlockQwen(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname in {"telegram_tts_bot.speech.qwen", "soundfile", "faster_qwen3_tts"}:
            raise ImportError("private dependency diagnostic")

sys.meta_path.insert(0, BlockQwen())
import telegram_tts_bot.__main__
import telegram_tts_bot.cli.tts_to_ogg
from telegram_tts_bot.speech import factory, SynthesisError
factory.FfmpegVoiceEncoder.verify_available = lambda self: None
try:
    factory.create_voice_renderer(Path("private-model"), Path("unused"), sys.argv[1], 1)
except SynthesisError as error:
    assert str(error) == "Qwen requires the GPU runtime dependencies"
    assert error.__suppress_context__
else:
    raise AssertionError("Qwen silently fell back")
""",
            voice,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert result.stderr == "qwen_runtime_dependencies_unavailable requires=gpu\n"
