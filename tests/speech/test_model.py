import hashlib
import urllib.error
import urllib.request
from pathlib import Path
from typing import Self

import pytest

from telegram_tts_bot.speech import model
from telegram_tts_bot.speech.silero import MODEL_SHA256


class Response:
    def __init__(self, data: bytes) -> None:
        self._data = data
        self._sent = False

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self, size: int) -> bytes:
        if self._sent:
            return b""
        self._sent = True
        return self._data


def test_provision_downloads_and_reuses_verified_asset(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    payload = b"model"
    asset = model.Asset("voice.pt", hashlib.sha256(payload).hexdigest())
    monkeypatch.setattr(model, "ASSETS", (asset,))
    calls = 0

    def urlopen(url: str, timeout: int) -> Response:
        nonlocal calls
        calls += 1
        assert "voice.pt" in url
        assert timeout == 60
        return Response(payload)

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)

    assert model.provision(tmp_path) == (tmp_path / "voice.pt",)
    assert model.provision(tmp_path) == (tmp_path / "voice.pt",)
    assert (tmp_path / "voice.pt").read_bytes() == payload
    assert calls == 1


def test_download_rejects_checksum_and_cleans_temp(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(model, "ASSETS", (model.Asset("voice", "0" * 64),))
    monkeypatch.setattr(urllib.request, "urlopen", lambda url, timeout: Response(b"bad"))

    with pytest.raises(ValueError, match="Checksum mismatch"):
        model.provision(tmp_path)
    assert not tuple(tmp_path.iterdir())


def test_model_main_reports_paths_and_failures(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = tmp_path / "models"
    monkeypatch.setattr(model, "provision", lambda path: (path / "voice",))
    assert model.main(["--output-dir", str(output)]) == 0
    assert str(output / "voice") in capsys.readouterr().out

    def fail(path: Path) -> tuple[Path, ...]:
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(model, "provision", fail)
    assert model.main(["--output-dir", str(output)]) == 1
    assert "Model provisioning failed" in capsys.readouterr().err


def test_pinned_model_coordinates_and_cli_default() -> None:
    assert len(model.ASSETS) == 1
    assert model.ASSETS[0] == model.Asset(model.MODEL_FILENAME, MODEL_SHA256)
    assert model.ASSETS[0].url == model.MODEL_URL
    assert model._parser().parse_args([]).output_dir == Path(".models/silero")
