import hashlib
import importlib
import logging
import os
import wave
from pathlib import Path

import pytest

from telegram_tts_bot.speech.errors import SynthesisError
from telegram_tts_bot.speech.piper import (
    PiperWaveSynthesizer,
    sha256_file,
    verify_assets,
)


class WavWritingVoice:
    def synthesize_wav(self, text: str, wav_file: wave.Wave_write) -> object:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(22050)
        wav_file.writeframes(text.encode())
        return None


def test_sha256_file_and_missing_asset(tmp_path: Path) -> None:
    asset = tmp_path / "asset"
    asset.write_bytes(b"voice")
    assert sha256_file(asset) == hashlib.sha256(b"voice").hexdigest()

    with pytest.raises(SynthesisError, match="unavailable"):
        sha256_file(tmp_path / "missing")


def test_verify_assets_rejects_each_bad_hash(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    model = tmp_path / "model.onnx"
    config = tmp_path / "model.onnx.json"

    monkeypatch.setattr("telegram_tts_bot.speech.piper.sha256_file", lambda path: "bad")
    with pytest.raises(SynthesisError, match=r"model\.onnx"):
        verify_assets(model, config)

    hashes = iter([
        "15fab56e11a097858ee115545d0f697fc2a316c41a291a5362349fb870411b0a",
        "bad",
    ])
    monkeypatch.setattr("telegram_tts_bot.speech.piper.sha256_file", lambda path: next(hashes))
    with pytest.raises(SynthesisError, match=r"model\.onnx\.json"):
        verify_assets(model, config)


def test_piper_load_forces_telemetry_off_before_import(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("ORT_DISABLE_TELEMETRY", "0")
    provider_logger = logging.getLogger("piper")
    monkeypatch.setattr(provider_logger, "level", logging.NOTSET)
    monkeypatch.setattr("telegram_tts_bot.speech.piper.verify_assets", lambda model, config: None)

    class VoiceClass:
        @staticmethod
        def load(*, model_path: Path, config_path: Path) -> WavWritingVoice:
            assert model_path.name == "model.onnx"
            assert config_path.name == "model.onnx.json"
            return WavWritingVoice()

    class PiperModule:
        PiperVoice = VoiceClass

    def fake_import(name: str) -> object:
        assert name == "piper"
        assert os.environ["ORT_DISABLE_TELEMETRY"] == "1"
        return PiperModule()

    monkeypatch.setattr(importlib, "import_module", fake_import)
    result = PiperWaveSynthesizer.load(tmp_path / "model.onnx", tmp_path / "model.onnx.json")
    assert isinstance(result.voice, WavWritingVoice)
    with caplog.at_level(logging.DEBUG):
        logging.getLogger("piper.voice").warning("text=%s", "PRIVATE_CLI_SENTINEL")
    assert provider_logger.level > logging.CRITICAL
    assert "PRIVATE_CLI_SENTINEL" not in caplog.text


def test_piper_load_maps_errors(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class ExternalPiperError(Exception):
        pass

    monkeypatch.setattr("telegram_tts_bot.speech.piper.verify_assets", lambda model, config: None)
    monkeypatch.setattr(
        importlib,
        "import_module",
        lambda name: (_ for _ in ()).throw(ExternalPiperError()),
    )
    with pytest.raises(SynthesisError, match="could not be loaded"):
        PiperWaveSynthesizer.load(tmp_path / "model", tmp_path / "config")


def test_piper_synthesizes_valid_wav_without_changing_text() -> None:
    audio = PiperWaveSynthesizer(WavWritingVoice()).synthesize(" точный ")
    assert audio.data.startswith(b"RIFF")
    assert " точный ".encode() in audio.data


def test_piper_maps_synthesis_error() -> None:
    class ExternalPiperError(Exception):
        pass

    class BrokenVoice:
        def synthesize_wav(self, text: str, wav_file: wave.Wave_write) -> object:
            raise ExternalPiperError("private")

    with pytest.raises(SynthesisError, match="failed") as captured:
        PiperWaveSynthesizer(BrokenVoice()).synthesize("do not expose")
    assert "do not expose" not in str(captured.value)
