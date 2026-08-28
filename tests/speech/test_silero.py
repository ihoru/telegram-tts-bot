import hashlib
import importlib
import io
import math
import struct
import wave
from contextlib import AbstractContextManager, nullcontext
from pathlib import Path
from typing import Any, cast

import pytest

from telegram_tts_bot.speech import silero
from telegram_tts_bot.speech.errors import SynthesisError
from telegram_tts_bot.speech.silero import (
    MAX_CHUNK_LENGTH,
    SileroWaveSynthesizer,
    _chunk_text,
    _model_spoken_text,
    sha256_file,
    verify_model,
)


class FakeNumpyArray:
    def __init__(self, samples: list[float | int]) -> None:
        self.samples = samples

    def astype(self, dtype: str, *, copy: bool) -> FakeNumpyArray:
        assert dtype == "<i2"
        assert copy is False
        return self

    def tobytes(self) -> bytes:
        return struct.pack(f"<{len(self.samples)}h", *(int(sample) for sample in self.samples))


class FakeTensor:
    def __init__(self, samples: list[float | int], *, ndim: int = 1) -> None:
        self.samples = samples
        self.ndim = ndim
        self.detached = False
        self.on_cpu = False

    def detach(self) -> FakeTensor:
        self.detached = True
        return self

    def numel(self) -> int:
        return len(self.samples)

    def all(self) -> FakeTensor:
        return FakeTensor([all(bool(sample) for sample in self.samples)])

    def item(self) -> object:
        assert len(self.samples) == 1
        return self.samples[0]

    def clamp(self, minimum: float, maximum: float) -> FakeTensor:
        self.samples = [min(maximum, max(minimum, sample)) for sample in self.samples]
        return self

    def mul(self, value: int) -> FakeTensor:
        self.samples = [sample * value for sample in self.samples]
        return self

    def round(self) -> FakeTensor:
        self.samples = [round(sample) for sample in self.samples]
        return self

    def to(self, *, device: str, dtype: object) -> FakeTensor:
        assert device == "cpu"
        assert dtype is FakeTorch.int16
        self.on_cpu = True
        return self

    def contiguous(self) -> FakeTensor:
        return self

    def numpy(self) -> FakeNumpyArray:
        return FakeNumpyArray(self.samples)


class FakeModel:
    speakers = ("kseniya", "xenia", "baya")

    def __init__(self, output: FakeTensor | None = None) -> None:
        self.output = output or FakeTensor([0.0])
        self.calls: list[dict[str, object]] = []
        self.device: object | None = None

    def to(self, device: object) -> FakeModel:
        self.device = device
        return self

    def apply_tts(
        self,
        *,
        text: str,
        speaker: str,
        sample_rate: int,
        put_accent: bool,
        put_yo: bool,
        put_stress_homo: bool,
        put_yo_homo: bool,
        stress_single_vowel: bool,
    ) -> FakeTensor:
        self.calls.append({
            "text": text,
            "speaker": speaker,
            "sample_rate": sample_rate,
            "put_accent": put_accent,
            "put_yo": put_yo,
            "put_stress_homo": put_stress_homo,
            "put_yo_homo": put_yo_homo,
            "stress_single_vowel": stress_single_vowel,
        })
        return self.output


class FakeTorch:
    int16 = object()

    def inference_mode(self) -> AbstractContextManager[object]:
        return nullcontext()

    def isfinite(self, tensor: FakeTensor) -> FakeTensor:
        return FakeTensor([math.isfinite(sample) for sample in tensor.samples])


def _synthesizer(model: FakeModel, speaker: str = "kseniya") -> SileroWaveSynthesizer:
    return SileroWaveSynthesizer(
        model=cast(Any, model),
        torch=cast(Any, FakeTorch()),
        speaker=speaker,
    )


def test_sha256_file_and_missing_model(tmp_path: Path) -> None:
    model = tmp_path / "model.pt"
    model.write_bytes(b"voice")
    assert sha256_file(model) == hashlib.sha256(b"voice").hexdigest()

    with pytest.raises(SynthesisError, match="unavailable") as caught:
        sha256_file(tmp_path / "private-model-name.pt")
    assert "private-model-name" not in str(caught.value)


def test_verify_model_rejects_checksum_before_import(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    model = tmp_path / "model.pt"
    model.write_bytes(b"wrong")

    def unexpected_import(_name: str) -> object:
        raise AssertionError("torch was imported before verification")

    monkeypatch.setattr(importlib, "import_module", unexpected_import)

    with pytest.raises(SynthesisError, match="checksum mismatch"):
        SileroWaveSynthesizer.load(model, "kseniya")


def test_verify_model_accepts_the_pinned_checksum(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    model = tmp_path / "model.pt"
    model.write_bytes(b"voice")
    monkeypatch.setattr(silero, "MODEL_SHA256", hashlib.sha256(b"voice").hexdigest())

    verify_model(model)


@pytest.mark.parametrize("speaker", ["kseniya", "xenia", "baya"])
def test_load_uses_packaged_cpu_model_and_fixed_warmup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    speaker: str,
) -> None:
    events: list[object] = []
    model = FakeModel()

    class Importer:
        def __init__(self, path: str) -> None:
            events.append(("importer", path))

        def load_pickle(self, package: str, resource: str) -> FakeModel:
            events.append(("pickle", package, resource))
            return model

    class Package:
        PackageImporter = Importer

    class Torch(FakeTorch):
        package = Package()

        def set_num_threads(self, threads: int) -> None:
            events.append(("threads", threads))

        def device(self, device: str) -> str:
            events.append(("device", device))
            return device

    monkeypatch.setattr(silero, "verify_model", lambda _path: events.append("verified"))
    monkeypatch.setattr(importlib, "import_module", lambda name: Torch())

    synthesizer = SileroWaveSynthesizer.load(tmp_path / "model.pt", speaker)

    assert synthesizer.model is model
    assert synthesizer.speaker == speaker
    assert events == [
        "verified",
        ("threads", 1),
        ("importer", str(tmp_path / "model.pt")),
        ("pickle", "tts_models", "model"),
        ("device", "cpu"),
    ]
    assert model.device == "cpu"
    assert model.calls == [
        {
            "text": "Короткая проверка готовности модели к синтезу.",
            "speaker": speaker,
            "sample_rate": 48_000,
            "put_accent": True,
            "put_yo": True,
            "put_stress_homo": True,
            "put_yo_homo": True,
            "stress_single_vowel": True,
        }
    ]


def test_load_validates_speaker_list_and_sanitizes_provider_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    model = FakeModel()

    class Importer:
        def __init__(self, _path: str) -> None:
            pass

        def load_pickle(self, _package: str, _resource: str) -> FakeModel:
            return model

    class Package:
        PackageImporter = Importer

    class Torch(FakeTorch):
        package = Package()

        def set_num_threads(self, _threads: int) -> None:
            pass

        def device(self, _device: str) -> str:
            return "cpu"

    monkeypatch.setattr(silero, "verify_model", lambda _path: None)
    monkeypatch.setattr(importlib, "import_module", lambda _name: Torch())

    with pytest.raises(SynthesisError, match="could not be loaded") as caught:
        SileroWaveSynthesizer.load(tmp_path / "model.pt", "private-speaker")
    assert "private-speaker" not in str(caught.value)

    monkeypatch.setattr(
        importlib,
        "import_module",
        lambda _name: (_ for _ in ()).throw(RuntimeError("private provider detail")),
    )
    with pytest.raises(SynthesisError, match="could not be loaded") as caught:
        SileroWaveSynthesizer.load(tmp_path / "model.pt", "kseniya")
    assert "private provider detail" not in str(caught.value)


@pytest.mark.parametrize("speaker", ["kseniya", "xenia", "baya"])
def test_synthesize_preserves_text_and_exact_inference_flags(speaker: str) -> None:
    model = FakeModel(FakeTensor([-2.0, -0.5, 0.0, 0.5, 2.0]))

    audio = _synthesizer(model, speaker).synthesize(" точный \N{EM DASH} текст ")

    assert model.calls == [
        {
            "text": " точный \N{EM DASH} текст ",
            "speaker": speaker,
            "sample_rate": 48_000,
            "put_accent": True,
            "put_yo": True,
            "put_stress_homo": True,
            "put_yo_homo": True,
            "stress_single_vowel": True,
        }
    ]
    with wave.open(io.BytesIO(audio.data), "rb") as wav_file:
        assert wav_file.getnchannels() == 1
        assert wav_file.getsampwidth() == 2
        assert wav_file.getframerate() == 48_000
        assert wav_file.getnframes() == 5
        assert struct.unpack("<5h", wav_file.readframes(5)) == (
            -32_767,
            -16_384,
            0,
            16_384,
            32_767,
        )
    assert model.output.detached
    assert model.output.on_cpu


@pytest.mark.parametrize(
    "tensor",
    [
        FakeTensor([], ndim=1),
        FakeTensor([0.0], ndim=2),
        FakeTensor([float("nan")]),
        FakeTensor([float("inf")]),
    ],
)
def test_synthesize_rejects_invalid_audio_privately(tensor: FakeTensor) -> None:
    with pytest.raises(SynthesisError, match="Silero synthesis failed") as caught:
        _synthesizer(FakeModel(tensor)).synthesize("private source text")

    assert "private source text" not in str(caught.value)


def test_synthesize_sanitizes_provider_exception() -> None:
    class BrokenModel(FakeModel):
        def apply_tts(
            self,
            *,
            text: str,
            speaker: str,
            sample_rate: int,
            put_accent: bool,
            put_yo: bool,
            put_stress_homo: bool,
            put_yo_homo: bool,
            stress_single_vowel: bool,
        ) -> FakeTensor:
            raise RuntimeError(text)

    with pytest.raises(SynthesisError, match="Silero synthesis failed") as caught:
        _synthesizer(BrokenModel()).synthesize("never expose this")

    assert "never expose this" not in str(caught.value)


@pytest.mark.parametrize(
    ("text", "spoken_text"),
    [
        ("Hello, WORLD!", "хелло, ворлд!"),
        ("Café", "кафе"),
        ("123", "один два три"),
        ("!?", "восклицательный знак вопросительный знак"),
        ("🙂", "символ юникод один два восемь пять семь восемь"),
    ],
)
def test_non_cyrillic_text_uses_deterministic_spoken_fallback(
    text: str,
    spoken_text: str,
) -> None:
    model = FakeModel(FakeTensor([0.0]))

    audio = _synthesizer(model).synthesize(text)

    assert _model_spoken_text(text) == spoken_text
    assert [call["text"] for call in model.calls] == [spoken_text]
    with wave.open(io.BytesIO(audio.data), "rb") as wav_file:
        assert wav_file.getnframes() == 1


def test_expanded_spoken_fallback_is_rechunked_before_inference() -> None:
    model = FakeModel(FakeTensor([0.0]))
    text = "9" * MAX_CHUNK_LENGTH
    spoken_text = _model_spoken_text(text)

    _synthesizer(model).synthesize(text)

    model_chunks = [cast(str, call["text"]) for call in model.calls]
    assert "".join(model_chunks) == spoken_text
    assert len(model_chunks) > 1
    assert all(0 < len(chunk) <= MAX_CHUNK_LENGTH for chunk in model_chunks)


def test_mixed_cyrillic_latin_and_digits_are_all_kept_speakable() -> None:
    model = FakeModel(FakeTensor([0.0]))
    text = "Привет, Hello 123!"

    _synthesizer(model).synthesize(text)

    assert [call["text"] for call in model.calls] == ["Привет, хелло один два три!"]


def test_non_cyrillic_fallback_failure_does_not_expose_source_or_normalized_text() -> None:
    class BrokenModel(FakeModel):
        def apply_tts(
            self,
            *,
            text: str,
            speaker: str,
            sample_rate: int,
            put_accent: bool,
            put_yo: bool,
            put_stress_homo: bool,
            put_yo_homo: bool,
            stress_single_vowel: bool,
        ) -> FakeTensor:
            raise RuntimeError(text)

    source_text = "PRIVATE 123!"
    normalized_text = _model_spoken_text(source_text)

    with pytest.raises(SynthesisError, match="Silero synthesis failed") as caught:
        _synthesizer(BrokenModel()).synthesize(source_text)

    assert source_text not in str(caught.value)
    assert normalized_text not in str(caught.value)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "a" * (MAX_CHUNK_LENGTH - 1),
        "a" * MAX_CHUNK_LENGTH,
        "a" * (MAX_CHUNK_LENGTH + 1),
        "я" * (MAX_CHUNK_LENGTH * 3 + 17),
        ("слово " * 400) + "конец",
    ],
)
def test_chunking_is_lossless_and_bounded(text: str) -> None:
    chunks = _chunk_text(text)

    assert "".join(chunks) == text
    assert all(0 < len(chunk) <= MAX_CHUNK_LENGTH for chunk in chunks)


def test_chunking_prefers_the_last_natural_boundary() -> None:
    text = ("a" * 300) + "." + ("b" * 300)

    chunks = _chunk_text(text)

    assert chunks == [("a" * 300) + ".", "b" * 300]


def test_long_text_synthesizes_multiple_chunks_into_one_wav() -> None:
    model = FakeModel(FakeTensor([0.25]))
    text = ("длинный текст. " * 100) + "конец"
    expected_chunks = _chunk_text(text)

    audio = _synthesizer(model).synthesize(text)
    rendered_chunks = [cast(str, call["text"]) for call in model.calls]

    assert rendered_chunks == expected_chunks
    assert "".join(rendered_chunks) == text
    assert all(len(chunk) <= MAX_CHUNK_LENGTH for chunk in rendered_chunks)
    with wave.open(io.BytesIO(audio.data), "rb") as wav_file:
        assert wav_file.getnchannels() == 1
        assert wav_file.getsampwidth() == 2
        assert wav_file.getframerate() == 48_000
        assert wav_file.getnframes() == len(expected_chunks)


def test_whitespace_only_chunks_do_not_call_the_model() -> None:
    model = FakeModel()

    audio = _synthesizer(model).synthesize(" " * (MAX_CHUNK_LENGTH * 2 + 1))

    assert model.calls == []
    with wave.open(io.BytesIO(audio.data), "rb") as wav_file:
        assert wav_file.getnframes() == 0
