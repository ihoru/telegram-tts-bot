from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from telegram_tts_bot.audition_archive import ArchiveError, validate_archive

ARCHIVE = Path(__file__).parents[1] / "auditions"


def _copy_archive(tmp_path: Path) -> Path:
    target = tmp_path / "auditions"
    shutil.copytree(ARCHIVE, target)
    return target


def _update_manifest(root: Path, update: Callable[[dict[str, object]], None]) -> None:
    path = root / "mixed-ru-en-v1" / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(manifest, dict)
    update(manifest)
    path.write_text(json.dumps(manifest), encoding="utf-8")


def _results(manifest: dict[str, object]) -> list[dict[str, object]]:
    value = manifest["results"]
    assert isinstance(value, list)
    assert all(isinstance(result, dict) for result in value)
    return value


def test_checked_in_audition_archive_is_valid() -> None:
    validate_archive(ARCHIVE)


def test_validator_rejects_prompt_drift(tmp_path: Path) -> None:
    root = _copy_archive(tmp_path)
    (root / "mixed-ru-en-v1" / "prompt.txt").write_text("changed\n", encoding="utf-8")

    with pytest.raises(ArchiveError, match="prompt hash mismatch"):
        validate_archive(root)


def test_validator_rejects_unlisted_and_missing_wavs(tmp_path: Path) -> None:
    root = _copy_archive(tmp_path)
    suite = root / "mixed-ru-en-v1"
    unlisted = suite / "results" / "extra.wav"
    shutil.copyfile(next(suite.glob("results/**/*.wav")), unlisted)

    with pytest.raises(ArchiveError, match="unlisted or missing WAVs"):
        validate_archive(root)

    unlisted.unlink()
    next(suite.glob("results/**/*.wav")).unlink()
    with pytest.raises(ArchiveError, match="missing or unsafe WAV"):
        validate_archive(root)


def test_validator_rejects_audio_hash_and_header_changes(tmp_path: Path) -> None:
    root = _copy_archive(tmp_path)
    audio = root / "mixed-ru-en-v1/results/piper-1.7.0-39ab474b/denis.wav"
    data = bytearray(audio.read_bytes())
    data[-1] ^= 1
    audio.write_bytes(data)

    with pytest.raises(ArchiveError, match="hash mismatch"):
        validate_archive(root)

    root = _copy_archive(tmp_path / "header")
    audio = root / "mixed-ru-en-v1/results/piper-1.7.0-39ab474b/denis.wav"
    data = bytearray(audio.read_bytes())
    data[:4] = b"NOPE"
    audio.write_bytes(data)
    _update_manifest(
        root,
        lambda manifest: _results(manifest)[0].update({"sha256": hashlib.sha256(data).hexdigest()}),
    )

    with pytest.raises(ArchiveError, match="invalid WAV"):
        validate_archive(root)


def test_validator_rejects_invalid_decision_history(tmp_path: Path) -> None:
    root = _copy_archive(tmp_path)
    _update_manifest(root, lambda manifest: _results(manifest)[0].update({"decision": "default"}))

    with pytest.raises(ArchiveError, match="stale decision"):
        validate_archive(root)


def test_validator_rejects_stale_metadata(tmp_path: Path) -> None:
    root = _copy_archive(tmp_path)
    _update_manifest(root, lambda manifest: _results(manifest)[0].update({"frames": 1}))

    with pytest.raises(ArchiveError, match="frame count mismatch"):
        validate_archive(root)
