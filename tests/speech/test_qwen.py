import importlib
import io
import logging
import os
import threading
import time
import wave
from concurrent.futures import ThreadPoolExecutor
from contextlib import AbstractContextManager, nullcontext
from pathlib import Path
from typing import Any, cast

import numpy as np
import pytest

from telegram_tts_bot.speech import qwen
from telegram_tts_bot.speech.errors import SynthesisError
from telegram_tts_bot.speech.qwen import (
    LANGUAGE,
    MAX_NEW_TOKENS,
    MAX_SEQUENCE_LENGTH,
    SEED,
    SPEAKER,
    WARMUP_PREFILL_LENGTH,
    QwenWaveSynthesizer,
)


class FakeCuda:
    def __init__(self, *, available: bool = True, bf16: bool = True) -> None:
        self.available = available
        self.bf16 = bf16
        self.seeds: list[int] = []

    def is_available(self) -> bool:
        return self.available

    def is_bf16_supported(self) -> bool:
        return self.bf16

    def manual_seed_all(self, seed: int) -> None:
        self.seeds.append(seed)


class FakeTorch:
    bfloat16 = object()

    def __init__(self, *, available: bool = True, bf16: bool = True) -> None:
        self.cuda = FakeCuda(available=available, bf16=bf16)
        self.seeds: list[int] = []

    def manual_seed(self, seed: int) -> None:
        self.seeds.append(seed)

    def inference_mode(self) -> AbstractContextManager[object]:
        return nullcontext()


class FakeModel:
    def __init__(self, waveform: object | None = None) -> None:
        self.waveform: object = np.array([-2.0, -0.5, 0.0, 0.5, 2.0], dtype=np.float32)
        if waveform is not None:
            self.waveform = waveform
        self.calls: list[dict[str, object]] = []
        self.active = 0
        self.max_active = 0
        self.warmup_calls: list[int] = []

    def warmup(self, prefill_len: int = 100) -> None:
        self.warmup_calls.append(prefill_len)

    def generate_custom_voice(self, **kwargs: object) -> tuple[list[object], int]:
        self.calls.append(kwargs)
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        time.sleep(0.005)
        self.active -= 1
        return [self.waveform], 24_000


def _synthesizer(model: FakeModel | None = None, *, speaker: str = SPEAKER) -> QwenWaveSynthesizer:
    return QwenWaveSynthesizer(
        model=cast(Any, model or FakeModel()),
        torch=cast(Any, FakeTorch()),
        speaker=speaker,
    )


def test_load_verifies_before_import_and_uses_exact_offline_cuda_arguments(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    events: list[object] = []
    torch_module = FakeTorch()
    model = FakeModel()

    class ModelClass:
        @staticmethod
        def from_pretrained(path: str, **kwargs: object) -> FakeModel:
            events.append(("load", path, kwargs))
            return model

    class QwenModule:
        FasterQwen3TTS = ModelClass()

    def import_module(name: str) -> object:
        events.append(("import", name))
        if name == "faster_qwen3_tts":
            print("optional upstream notice")
        return torch_module if name == "torch" else QwenModule()

    monkeypatch.setattr(
        qwen, "verify_model_directory", lambda path: events.append(("verify", path))
    )
    monkeypatch.setattr(importlib, "import_module", import_module)
    for name in qwen._OFFLINE_ENVIRONMENT:
        monkeypatch.setenv(name, "0")
    monkeypatch.chdir(tmp_path)
    caplog.set_level(logging.INFO, logger=qwen.LOGGER.name)

    synthesizer = QwenWaveSynthesizer.load(tmp_path / "model")

    assert synthesizer.model is model
    assert synthesizer.speaker == "Aiden"
    assert events == [
        ("verify", tmp_path / "model"),
        ("import", "torch"),
        ("import", "faster_qwen3_tts"),
        (
            "load",
            str(tmp_path / "model"),
            {
                "device": "cuda:0",
                "dtype": torch_module.bfloat16,
                "attn_implementation": "sdpa",
                "max_seq_len": MAX_SEQUENCE_LENGTH,
                "local_files_only": True,
            },
        ),
    ]
    assert model.warmup_calls == [WARMUP_PREFILL_LENGTH]
    assert all(os.environ[name] == "1" for name in qwen._OFFLINE_ENVIRONMENT)
    assert not (tmp_path / ":memory:.ses").exists()
    assert capsys.readouterr().out == ""
    assert [record.getMessage().split(" in ")[0] for record in caplog.records] == [
        "loading Qwen model",
        "Qwen model loaded",
    ]


@pytest.mark.parametrize(("available", "bf16"), [(False, True), (True, False)])
def test_load_rejects_missing_cuda_privately(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    available: bool,
    bf16: bool,
) -> None:
    monkeypatch.setattr(qwen, "verify_model_directory", lambda _path: None)
    monkeypatch.setattr(
        importlib, "import_module", lambda _name: FakeTorch(available=available, bf16=bf16)
    )

    with pytest.raises(SynthesisError, match="could not be loaded") as caught:
        QwenWaveSynthesizer.load(tmp_path / "private-model")

    assert "private-model" not in str(caught.value)


def test_load_rejects_checksum_before_import(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        qwen,
        "verify_model_directory",
        lambda _path: (_ for _ in ()).throw(ValueError("private checksum detail")),
    )
    monkeypatch.setattr(
        importlib,
        "import_module",
        lambda _name: (_ for _ in ()).throw(AssertionError("unexpected import")),
    )

    with pytest.raises(SynthesisError, match="could not be loaded") as caught:
        QwenWaveSynthesizer.load(tmp_path / "model")

    assert "private checksum detail" not in str(caught.value)


@pytest.mark.parametrize("speaker", ["Aiden", "Serena"])
def test_synthesize_preserves_mixed_text_and_writes_exact_pcm16_wav(speaker: str) -> None:
    model = FakeModel()
    synthesizer = _synthesizer(model, speaker=speaker)

    audio = synthesizer.synthesize("Привет, deployment strategy!")

    assert model.calls == [
        {
            "text": "Привет, deployment strategy!",
            "language": LANGUAGE,
            "speaker": speaker,
            "instruct": "",
            "max_new_tokens": MAX_NEW_TOKENS,
        }
    ]
    assert cast(FakeTorch, synthesizer.torch).seeds == [SEED]
    assert cast(FakeTorch, synthesizer.torch).cuda.seeds == [SEED]
    with wave.open(io.BytesIO(audio.data), "rb") as wav_file:
        assert wav_file.getnchannels() == 1
        assert wav_file.getsampwidth() == 2
        assert wav_file.getframerate() == 24_000
        assert (
            wav_file.readframes(5)
            == np.array([-32_768, -16_384, 0, 16_384, 32_767], dtype="<i2").tobytes()
        )


def test_long_text_is_losslessly_chunked_and_seeded_once() -> None:
    model = FakeModel(np.array([0.0], dtype=np.float32))
    synthesizer = _synthesizer(model)
    text = ("Русский text. " * 100) + "конец"

    synthesizer.synthesize(text)

    chunks = [cast(str, call["text"]) for call in model.calls]
    assert "".join(chunks) == text
    assert len(chunks) > 1
    assert all(0 < len(chunk) <= 500 for chunk in chunks)
    assert cast(FakeTorch, synthesizer.torch).seeds == [SEED]


def test_long_text_reports_content_free_chunk_progress(
    caplog: pytest.LogCaptureFixture,
) -> None:
    model = FakeModel(np.array([0.0], dtype=np.float32))
    synthesizer = _synthesizer(model)
    text = ("private Русский text. " * 60) + "конец"
    caplog.set_level(logging.INFO, logger=qwen.LOGGER.name)

    synthesizer.synthesize(text)

    messages = [record.getMessage() for record in caplog.records]
    assert messages[0].startswith("generating Qwen audio: ")
    assert messages[-1].startswith("Qwen audio complete: ")
    assert sum(message.startswith("generating Qwen chunk ") for message in messages) == len(
        model.calls
    )
    assert f"{len(model.calls)}/{len(model.calls)}" in messages[-2]
    assert "private" not in "\n".join(messages)


def test_inference_is_serialized() -> None:
    model = FakeModel(np.array([0.0], dtype=np.float32))
    synthesizer = _synthesizer(model)
    barrier = threading.Barrier(3)

    def render() -> None:
        barrier.wait()
        synthesizer.synthesize("Привет, API!")

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(render) for _ in range(2)]
        barrier.wait()
        for future in futures:
            future.result()

    assert model.max_active == 1


@pytest.mark.parametrize(
    "waveform",
    [
        np.array([], dtype=np.float32),
        np.array([[0.0]], dtype=np.float32),
        np.array([np.nan], dtype=np.float32),
        np.array([np.inf], dtype=np.float32),
    ],
)
def test_invalid_audio_is_rejected_without_source_text(waveform: object) -> None:
    with pytest.raises(SynthesisError, match="Qwen synthesis failed") as caught:
        _synthesizer(FakeModel(waveform)).synthesize("private mixed text")
    assert "private mixed text" not in str(caught.value)


def test_whitespace_only_input_produces_no_audio() -> None:
    with pytest.raises(SynthesisError, match="Qwen synthesis failed"):
        _synthesizer().synthesize("  \n")
