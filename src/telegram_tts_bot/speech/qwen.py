"""Qwen3-TTS CustomVoice waveform synthesis adapter."""

from __future__ import annotations

import importlib
import io
import logging
import os
import threading
from collections.abc import Sequence
from contextlib import AbstractContextManager, redirect_stdout
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Protocol, cast

import numpy as np
import numpy.typing as npt
import soundfile as sf  # type: ignore[import-untyped]

from telegram_tts_bot.speech.chunking import chunk_text
from telegram_tts_bot.speech.errors import SynthesisError
from telegram_tts_bot.speech.types import WavAudio

SPEAKER = "Aiden"
SUPPORTED_SPEAKERS = {"aiden": "Aiden", "serena": "Serena"}
LANGUAGE = "Auto"
SEED = 20_260_828
MAX_NEW_TOKENS = 2_048
MAX_SEQUENCE_LENGTH = 2_048
WARMUP_PREFILL_LENGTH = 100
LOGGER = logging.getLogger(__name__)
_OFFLINE_ENVIRONMENT = {
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
    "HF_HUB_DISABLE_TELEMETRY": "1",
    "DO_NOT_TRACK": "1",
    "ORT_DISABLE_TELEMETRY": "1",
}


class _CudaModule(Protocol):
    def is_available(self) -> bool:
        """Return whether a CUDA device is available."""

    def is_bf16_supported(self) -> bool:
        """Return whether the active CUDA device supports BF16."""

    def manual_seed_all(self, seed: int) -> None:
        """Seed all CUDA generators."""


class _TorchModule(Protocol):
    bfloat16: object
    cuda: _CudaModule

    def manual_seed(self, seed: int) -> object:
        """Seed the CPU generator."""

    def inference_mode(self) -> AbstractContextManager[object]:
        """Disable gradient tracking."""


class _QwenModel(Protocol):
    def warmup(self, prefill_len: int = 100) -> None:
        """Capture the CUDA graphs before serving requests."""

    def generate_custom_voice(
        self,
        *,
        text: str,
        language: str,
        speaker: str,
        instruct: str,
        max_new_tokens: int,
    ) -> tuple[Sequence[object], int]:
        """Generate one waveform."""


class _QwenModelClass(Protocol):
    def from_pretrained(self, model_path: str, **kwargs: object) -> _QwenModel:
        """Load one local model."""


class _QwenModule(Protocol):
    FasterQwen3TTS: _QwenModelClass


def _set_offline_environment() -> None:
    for name, value in _OFFLINE_ENVIRONMENT.items():
        os.environ[name] = value


def verify_model_directory(model_path: Path) -> None:
    """Lazily verify the snapshot so the provisioner remains directly runnable."""
    from telegram_tts_bot.speech.qwen_model import verify_model_directory as verify

    verify(model_path)


def _validated_waveform(waveform: object) -> npt.NDArray[np.float32]:
    samples = np.asarray(waveform, dtype=np.float32)
    if samples.ndim != 1 or samples.size == 0 or not bool(np.isfinite(samples).all()):
        raise ValueError("invalid Qwen audio")
    return np.clip(samples, -1.0, 1.0)


def _wav_from_samples(samples: npt.NDArray[np.float32], sample_rate: int) -> WavAudio:
    if sample_rate <= 0 or samples.size == 0:
        raise ValueError("invalid Qwen audio")
    with io.BytesIO() as buffer:
        sf.write(buffer, samples, sample_rate, format="WAV", subtype="PCM_16")
        return WavAudio(data=buffer.getvalue())


@dataclass(slots=True)
class QwenWaveSynthesizer:
    """Adapt one loaded Qwen CustomVoice model to the engine-neutral contract."""

    model: _QwenModel
    torch: _TorchModule
    speaker: str = SPEAKER
    _inference_lock: threading.Lock = field(default_factory=threading.Lock)

    @classmethod
    def load(cls, model_path: Path, speaker: str = "aiden") -> QwenWaveSynthesizer:
        """Verify the local snapshot, require CUDA BF16, and load one speaker."""
        started_at = perf_counter()
        LOGGER.info("loading Qwen model")
        try:
            selected_speaker = SUPPORTED_SPEAKERS[speaker]
            verify_model_directory(model_path)
            _set_offline_environment()
            torch_module = cast(_TorchModule, importlib.import_module("torch"))
            if not torch_module.cuda.is_available() or not torch_module.cuda.is_bf16_supported():
                raise ValueError("CUDA BF16 is unavailable")
            with redirect_stdout(io.StringIO()):
                qwen_module = cast(_QwenModule, importlib.import_module("faster_qwen3_tts"))
                model = qwen_module.FasterQwen3TTS.from_pretrained(
                    str(model_path),
                    device="cuda:0",
                    dtype=torch_module.bfloat16,
                    attn_implementation="sdpa",
                    max_seq_len=MAX_SEQUENCE_LENGTH,
                    local_files_only=True,
                )
                model.warmup(prefill_len=WARMUP_PREFILL_LENGTH)
        except Exception:
            raise SynthesisError("Qwen model could not be loaded") from None
        LOGGER.info("Qwen model loaded in %.1f seconds", perf_counter() - started_at)
        return cls(model=model, torch=torch_module, speaker=selected_speaker)

    def synthesize(self, text: str, /) -> WavAudio:
        """Create one complete in-memory mono PCM16 WAV file."""
        try:
            chunks = [chunk for chunk in chunk_text(text) if chunk.strip()]
            unit = "chunk" if len(chunks) == 1 else "chunks"
            LOGGER.info("generating Qwen audio: %d %s", len(chunks), unit)
            audio_chunks: list[npt.NDArray[np.float32]] = []
            sample_rate: int | None = None
            with self._inference_lock, self.torch.inference_mode():
                self.torch.manual_seed(SEED)
                self.torch.cuda.manual_seed_all(SEED)
                for index, chunk in enumerate(chunks, start=1):
                    LOGGER.info("generating Qwen chunk %d/%d", index, len(chunks))
                    generated, current_rate = self.model.generate_custom_voice(
                        text=chunk,
                        language=LANGUAGE,
                        speaker=self.speaker,
                        instruct="",
                        max_new_tokens=MAX_NEW_TOKENS,
                    )
                    if len(generated) != 1:
                        raise ValueError("invalid Qwen output count")
                    if sample_rate is None:
                        sample_rate = current_rate
                    elif current_rate != sample_rate:
                        raise ValueError("Qwen sample rate changed")
                    audio_chunks.append(_validated_waveform(generated[0]))
            if sample_rate is None:
                raise ValueError("Qwen produced no audio")
            audio = _wav_from_samples(np.concatenate(audio_chunks), sample_rate)
            LOGGER.info("Qwen audio complete: %d/%d chunks", len(chunks), len(chunks))
            return audio
        except Exception:
            raise SynthesisError("Qwen synthesis failed") from None
