"""Validate immutable voice-audition fixtures without model or network access."""

from __future__ import annotations

import hashlib
import json
import sys
import wave
from datetime import date, datetime
from pathlib import Path, PurePosixPath
from typing import Any

ALLOWED_DECISIONS = {"default", "rejected", "removed", "retained", "selected"}
REQUIRED_RESULT_FIELDS = {
    "adapter_revision",
    "auditioned_on",
    "bytes",
    "decision",
    "decision_history",
    "duration_seconds",
    "engine",
    "engine_version",
    "frames",
    "id",
    "license",
    "model",
    "model_revision",
    "path",
    "rendered_at",
    "runtime",
    "sample_rate_hz",
    "sha256",
    "source",
    "speaker",
}


class ArchiveError(ValueError):
    """The archive does not satisfy its integrity contract."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ArchiveError(message)


def _object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ArchiveError(f"{label} must be an object")
    return value


def _list(value: object, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ArchiveError(f"{label} must be an array")
    return value


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ArchiveError(f"cannot read {path}: {error}") from error
    return _object(value, str(path))


def _logical_prompt(path: Path) -> bytes:
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise ArchiveError(f"cannot read prompt {path}: {error}") from error
    return raw[:-1] if raw.endswith(b"\n") else raw


def _safe_relative_path(value: object) -> PurePosixPath:
    if not isinstance(value, str):
        raise ArchiveError("result path must be a string")
    path = PurePosixPath(value)
    _require(not path.is_absolute(), f"absolute result path: {value}")
    _require(".." not in path.parts and "." not in path.parts, f"unsafe result path: {value}")
    _require(path.suffix == ".wav", f"result is not a WAV path: {value}")
    return path


def _validate_dates(result: dict[str, Any]) -> None:
    result_id = result["id"]
    try:
        date.fromisoformat(result["auditioned_on"])
        rendered_at = datetime.fromisoformat(result["rendered_at"])
    except (TypeError, ValueError) as error:
        raise ArchiveError(f"invalid chronology for {result_id}") from error
    _require(rendered_at.tzinfo is not None, f"rendered_at lacks timezone for {result_id}")

    history = _list(result["decision_history"], f"decision_history for {result_id}")
    _require(bool(history), f"empty decision_history for {result_id}")
    previous: date | None = None
    for event_value in history:
        event = _object(event_value, f"decision event for {result_id}")
        _require(set(event) >= {"date", "decision", "reason"}, f"incomplete event for {result_id}")
        try:
            event_date = date.fromisoformat(event["date"])
        except (TypeError, ValueError) as error:
            raise ArchiveError(f"invalid event date for {result_id}") from error
        _require(event["decision"] in ALLOWED_DECISIONS, f"invalid event decision for {result_id}")
        _require(
            isinstance(event["reason"], str) and bool(event["reason"]),
            f"empty reason for {result_id}",
        )
        _require(
            previous is None or event_date >= previous, f"out-of-order history for {result_id}"
        )
        previous = event_date
    _require(result["decision"] == history[-1]["decision"], f"stale decision for {result_id}")


def _validate_wav(suite: Path, result: dict[str, Any], relative: PurePosixPath) -> None:
    audio_path = suite.joinpath(*relative.parts)
    _require(
        audio_path.is_file() and not audio_path.is_symlink(), f"missing or unsafe WAV: {relative}"
    )
    data = audio_path.read_bytes()
    _require(len(data) == result["bytes"], f"byte count mismatch: {relative}")
    _require(hashlib.sha256(data).hexdigest() == result["sha256"], f"hash mismatch: {relative}")

    try:
        with wave.open(str(audio_path), "rb") as audio:
            _require(audio.getnchannels() == 1, f"WAV is not mono: {relative}")
            _require(audio.getsampwidth() == 2, f"WAV is not PCM16: {relative}")
            _require(audio.getcomptype() == "NONE", f"WAV is compressed: {relative}")
            _require(
                audio.getframerate() == result["sample_rate_hz"],
                f"sample rate mismatch: {relative}",
            )
            _require(audio.getnframes() == result["frames"], f"frame count mismatch: {relative}")
    except (EOFError, wave.Error) as error:
        raise ArchiveError(f"invalid WAV: {relative}") from error

    duration = result["frames"] / result["sample_rate_hz"]
    _require(
        abs(duration - result["duration_seconds"]) <= 0.000001, f"duration mismatch: {relative}"
    )


def validate_suite(suite: Path) -> None:
    manifest = _load_manifest(suite / "manifest.json")
    _require(manifest.get("schema_version") == 1, f"unsupported schema in {suite}")
    prompt = _object(manifest.get("prompt"), f"prompt metadata in {suite}")
    prompt_path = suite / prompt.get("path", "")
    logical_prompt = _logical_prompt(prompt_path)
    _require(
        hashlib.sha256(logical_prompt).hexdigest() == prompt.get("sha256"), "prompt hash mismatch"
    )
    try:
        decoded_prompt = logical_prompt.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ArchiveError("prompt is not UTF-8") from error
    _require(len(decoded_prompt) == prompt.get("codepoints"), "prompt codepoint count mismatch")

    results = _list(manifest.get("results"), f"results in {suite}")
    _require(bool(results), f"no results in {suite}")
    seen_ids: set[str] = set()
    seen_paths: set[PurePosixPath] = set()
    for value in results:
        result = _object(value, f"result in {suite}")
        _require(set(result) >= REQUIRED_RESULT_FIELDS, f"incomplete result in {suite}")
        result_id = result["id"]
        _require(isinstance(result_id, str) and bool(result_id), f"invalid result id in {suite}")
        _require(result_id not in seen_ids, f"duplicate result id: {result_id}")
        seen_ids.add(result_id)
        relative = _safe_relative_path(result["path"])
        _require(relative not in seen_paths, f"duplicate result path: {relative}")
        seen_paths.add(relative)
        _require(result["decision"] in ALLOWED_DECISIONS, f"invalid decision for {result_id}")
        _validate_dates(result)
        _validate_wav(suite, result, relative)

    discovered = {
        PurePosixPath(path.relative_to(suite).as_posix()) for path in suite.glob("results/**/*.wav")
    }
    _require(discovered == seen_paths, f"unlisted or missing WAVs in {suite}")


def validate_archive(root: Path) -> None:
    manifests = sorted(root.glob("*/manifest.json"))
    _require(bool(manifests), f"no audition manifests under {root}")
    for manifest in manifests:
        validate_suite(manifest.parent)


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) == 2 else Path("auditions")
    try:
        validate_archive(root)
    except ArchiveError as error:
        print(f"audition archive invalid: {error}", file=sys.stderr)
        return 1
    print(f"audition archive valid: {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
