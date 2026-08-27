"""Piper-specific waveform synthesis adapter."""

import hashlib
import importlib
import io
import logging
import os
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

from telegram_tts_bot.speech.errors import SynthesisError
from telegram_tts_bot.speech.types import WavAudio

MODEL_SHA256 = "15fab56e11a097858ee115545d0f697fc2a316c41a291a5362349fb870411b0a"
CONFIG_SHA256 = "831c860dac0b5073eaa81610a0a638ec23d90a6cf8e5f871b4485c2cec3767c8"


class _PiperVoice(Protocol):
    def synthesize_wav(self, text: str, wav_file: wave.Wave_write) -> object:
        """Write synthesized audio into an open WAV writer."""


def sha256_file(path: Path) -> str:
    """Hash an asset without loading it all into memory."""
    digest = hashlib.sha256()
    try:
        with path.open("rb") as asset:
            for chunk in iter(lambda: asset.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise SynthesisError(f"Speech asset is unavailable: {path.name}") from error
    return digest.hexdigest()


def verify_assets(model_path: Path, config_path: Path) -> None:
    """Verify the fixed v1 voice before loading executable model data."""
    if sha256_file(model_path) != MODEL_SHA256:
        raise SynthesisError(f"Speech asset checksum mismatch: {model_path.name}")
    if sha256_file(config_path) != CONFIG_SHA256:
        raise SynthesisError(f"Speech asset checksum mismatch: {config_path.name}")


@dataclass(slots=True)
class PiperWaveSynthesizer:
    """Adapt one loaded Piper voice to the engine-neutral contract."""

    voice: _PiperVoice

    @classmethod
    def load(cls, model_path: Path, config_path: Path) -> PiperWaveSynthesizer:
        """Verify and load a Piper voice without enabling ONNX telemetry."""
        verify_assets(model_path, config_path)

        # ONNX Runtime 1.29 otherwise persists a telemetry identifier in the cwd on Linux.
        os.environ["ORT_DISABLE_TELEMETRY"] = "1"
        # Piper logs source text and input-derived phonemes at DEBUG/WARNING. Suppress
        # provider output for both the bot and the standalone CLI before importing it.
        logging.getLogger("piper").setLevel(logging.CRITICAL + 1)
        try:
            piper_module = importlib.import_module("piper")
            voice_class = piper_module.PiperVoice
            voice = cast(
                _PiperVoice,
                voice_class.load(model_path=model_path, config_path=config_path),
            )
        except Exception as error:
            raise SynthesisError("Piper voice could not be loaded") from error
        return cls(voice=voice)

    def synthesize(self, text: str, /) -> WavAudio:
        """Create a complete in-memory WAV file."""
        try:
            with io.BytesIO() as buffer:
                with wave.open(buffer, "wb") as wav_file:
                    self.voice.synthesize_wav(text, wav_file)
                return WavAudio(data=buffer.getvalue())
        except Exception as error:
            raise SynthesisError("Piper synthesis failed") from error
