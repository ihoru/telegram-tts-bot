import hashlib
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import ClassVar

import pytest

from telegram_tts_bot.speech import qwen_model
from telegram_tts_bot.speech.qwen_model import Asset, ModelVerificationError


def _asset(filename: str, content: bytes) -> Asset:
    return Asset(filename, hashlib.sha256(content).hexdigest())


def test_module_entrypoint_does_not_preimport_itself() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "telegram_tts_bot.speech.qwen_model", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert "RuntimeWarning" not in completed.stderr


def test_pinned_manifest_contains_the_complete_snapshot() -> None:
    assert len(qwen_model.ASSETS) == 11
    assert qwen_model.MODEL_REVISION == "85e237c12c027371202489a0ec509ded67b5e4b5"
    assert {asset.filename for asset in qwen_model.ASSETS} == {
        "config.json",
        "generation_config.json",
        "merges.txt",
        "model.safetensors",
        "preprocessor_config.json",
        "speech_tokenizer/config.json",
        "speech_tokenizer/configuration.json",
        "speech_tokenizer/model.safetensors",
        "speech_tokenizer/preprocessor_config.json",
        "tokenizer_config.json",
        "vocab.json",
    }


def test_verify_model_directory_accepts_only_exact_regular_files(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    assets = (_asset("config.json", b"config"), _asset("nested/model.bin", b"model"))
    monkeypatch.setattr(qwen_model, "ASSETS", assets)
    model = tmp_path / "model"
    (model / "nested").mkdir(parents=True)
    (model / "config.json").write_bytes(b"config")
    (model / "nested/model.bin").write_bytes(b"model")

    qwen_model.verify_model_directory(model)

    (model / "extra.txt").write_text("extra", encoding="utf-8")
    with pytest.raises(ModelVerificationError, match="file set"):
        qwen_model.verify_model_directory(model)


def test_verify_model_directory_rejects_missing_bad_and_symlinked_files(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    asset = _asset("model.bin", b"correct")
    monkeypatch.setattr(qwen_model, "ASSETS", (asset,))
    model = tmp_path / "model"

    with pytest.raises(ModelVerificationError, match="unavailable"):
        qwen_model.verify_model_directory(model)

    model.mkdir()
    (model / "model.bin").write_bytes(b"wrong")
    with pytest.raises(ModelVerificationError, match="checksum"):
        qwen_model.verify_model_directory(model)

    (model / "model.bin").unlink()
    target = tmp_path / "target.bin"
    target.write_bytes(b"correct")
    (model / "model.bin").symlink_to(target)
    with pytest.raises(ModelVerificationError, match="checksum"):
        qwen_model.verify_model_directory(model)


def test_provision_reuses_a_verified_directory_without_download(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    asset = _asset("model.bin", b"model")
    monkeypatch.setattr(qwen_model, "ASSETS", (asset,))
    model = tmp_path / "model"
    model.mkdir()
    (model / "model.bin").write_bytes(b"model")
    monkeypatch.setattr(
        qwen_model,
        "_download",
        lambda *_args: (_ for _ in ()).throw(AssertionError("unexpected download")),
    )

    assert qwen_model.provision(model) == model.resolve()


def test_provision_installs_complete_snapshot_and_cleans_failed_staging(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    assets = (_asset("config.json", b"config"), _asset("nested/model.bin", b"model"))
    monkeypatch.setattr(qwen_model, "ASSETS", assets)

    def download(asset: Asset, staging: Path) -> None:
        destination = staging / asset.filename
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(
            {"config.json": b"config", "nested/model.bin": b"model"}[asset.filename]
        )

    monkeypatch.setattr(qwen_model, "_download", download)
    output = tmp_path / "model"

    assert qwen_model.provision(output) == output.resolve()
    qwen_model.verify_model_directory(output)
    assert not tuple(tmp_path.glob(".model.*"))

    failed = tmp_path / "failed"
    monkeypatch.setattr(
        qwen_model,
        "_download",
        lambda *_args: (_ for _ in ()).throw(OSError("download failed")),
    )
    with pytest.raises(OSError, match="download failed"):
        qwen_model.provision(failed)
    assert not failed.exists()
    assert not tuple(tmp_path.glob(".failed.*"))


def test_download_reports_monotonic_byte_progress(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    content = b"model" * 300_000
    asset = _asset("model.bin", content)
    reports: list[tuple[int, int | None, bool]] = []
    requested_sizes: list[int] = []

    class Response:
        headers: ClassVar[dict[str, str]] = {"Content-Length": str(len(content))}
        offset = 0

        def __enter__(self) -> Response:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self, size: int) -> bytes:
            requested_sizes.append(size)
            chunk = content[self.offset : self.offset + size]
            self.offset += len(chunk)
            return chunk

    monkeypatch.setattr(urllib.request, "urlopen", lambda *_args, **_kwargs: Response())

    qwen_model._download(
        asset,
        tmp_path,
        progress=lambda done, total, complete: reports.append((done, total, complete)),
    )

    assert reports[0] == (0, len(content), False)
    assert reports[-1] == (len(content), len(content), True)
    assert [done for done, _total, _complete in reports] == sorted(
        done for done, _total, _complete in reports
    )
    assert set(requested_sizes) == {64 * 1024}


def test_main_shows_download_progress_and_keeps_path_on_stdout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    asset = _asset("model.bin", b"model")
    output = tmp_path / "model"

    def provision(
        path: Path,
        *,
        progress: qwen_model.ProvisionProgress | None = None,
    ) -> Path:
        assert progress is not None
        progress(1, 1, asset, 1024 * 1024, 2 * 1024**3, False)
        progress(1, 1, asset, 2 * 1024**3, 2 * 1024**3, True)
        return path.resolve()

    monkeypatch.setattr(qwen_model, "provision", provision)

    assert qwen_model.main(["--output-dir", str(output)]) == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == str(output.resolve())
    assert "Downloading 1/1 model.bin: 1.0 MiB / 2.0 GiB (0%)" in captured.err
    assert captured.err.endswith("2.0 GiB / 2.0 GiB (100%)\n")
    assert "2,147,483,648" not in captured.err


def test_main_handles_ctrl_c_without_traceback(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        qwen_model,
        "provision",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(KeyboardInterrupt),
    )

    assert qwen_model.main([]) == 130
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "\nQwen model provisioning cancelled.\n"
    assert "Traceback" not in captured.err


def test_interrupted_provision_removes_partial_staging(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def interrupt(_asset: Asset, staging: Path) -> None:
        (staging / "partial.bin").write_bytes(b"partial")
        raise KeyboardInterrupt

    monkeypatch.setattr(qwen_model, "_download", interrupt)

    with pytest.raises(KeyboardInterrupt):
        qwen_model.provision(tmp_path / "model")

    assert not tuple(tmp_path.glob(".model.*"))
