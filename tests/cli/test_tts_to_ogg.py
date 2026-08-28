import asyncio
import importlib
import io
import os
import sys
from collections.abc import Coroutine
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from telegram_tts_bot.cli import tts_to_ogg


def test_read_stdin_preserves_text_and_rejects_invalid_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(" текст ".encode())))
    assert tts_to_ogg._read_stdin() == " текст "

    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(b"\xff")))
    with pytest.raises(ValueError, match="UTF-8"):
        tts_to_ogg._read_stdin()

    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(b" \n")))
    with pytest.raises(ValueError, match="non-whitespace"):
        tts_to_ogg._read_stdin()


def test_cli_writes_resolved_output_without_telegram_token(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def render(text: str) -> bytes:
        await asyncio.sleep(0)
        assert text == "a" * 5000
        return b"ogg"

    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setattr(tts_to_ogg, "_read_stdin", lambda: "a" * 5000)
    monkeypatch.setattr(tts_to_ogg, "_render", render)
    output = tmp_path / "sample.ogg"

    assert tts_to_ogg.main([str(output)]) == 0
    assert output.read_bytes() == b"ogg"
    assert capsys.readouterr().out.strip() == str(output.resolve())


def test_cli_validates_path_before_rendering(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    rendered = False

    async def render(text: str) -> bytes:
        nonlocal rendered
        await asyncio.sleep(0)
        rendered = True
        return b"ogg"

    monkeypatch.setattr(tts_to_ogg, "_read_stdin", lambda: "text")
    monkeypatch.setattr(tts_to_ogg, "_render", render)
    output = tmp_path / "missing" / "sample.ogg"

    assert tts_to_ogg.main([str(output)]) == 2
    assert not rendered
    assert "parent directory" in capsys.readouterr().err


def test_cli_validates_input_and_path_before_importing_torch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    imported = False

    def unexpected_import(_name: str) -> object:
        nonlocal imported
        imported = True
        raise AssertionError("torch must remain lazy")

    monkeypatch.setattr(importlib, "import_module", unexpected_import)
    monkeypatch.setattr(tts_to_ogg, "_read_stdin", lambda: "text")

    assert tts_to_ogg.main([str(tmp_path / "missing" / "sample.ogg")]) == 2
    assert not imported


def test_cli_wires_silero_environment_without_telegram_token(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[object] = []

    class Renderer:
        async def render(self, text: str) -> object:
            calls.append(text)
            return SimpleNamespace(data=b"ogg")

        async def close(self) -> None:
            calls.append("closed")

    def renderer_factory(**kwargs: object) -> Renderer:
        calls.append(kwargs)
        return Renderer()

    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setenv("SILERO_MODEL_PATH", str(tmp_path / "model.pt"))
    monkeypatch.setenv("TTS_VOICE", "xenia")
    monkeypatch.setattr(tts_to_ogg, "create_voice_renderer", renderer_factory)

    assert asyncio.run(tts_to_ogg._render("private text")) == b"ogg"
    assert calls == [
        {
            "model_path": (tmp_path / "model.pt").resolve(),
            "speaker": "xenia",
            "max_workers": 1,
        },
        "private text",
        "closed",
    ]


def test_cli_rejects_unsupported_voice_after_input_validation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("TTS_VOICE", "denis")
    monkeypatch.setattr(tts_to_ogg, "_read_stdin", lambda: "text")
    output = tmp_path / "sample.ogg"

    assert tts_to_ogg.main([str(output)]) == 2
    assert not output.exists()
    assert "kseniya, xenia, baya" in capsys.readouterr().err


def test_cli_refuses_overwrite_and_force_replaces_atomically(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    async def render(text: str) -> bytes:
        await asyncio.sleep(0)
        return b"new"

    monkeypatch.setattr(tts_to_ogg, "_read_stdin", lambda: "text")
    monkeypatch.setattr(tts_to_ogg, "_render", render)
    output = tmp_path / "sample.ogg"
    output.write_bytes(b"old")

    assert tts_to_ogg.main([str(output)]) == 2
    assert output.read_bytes() == b"old"
    assert tts_to_ogg.main([str(output), "--force"]) == 0
    assert output.read_bytes() == b"new"
    assert not tuple(tmp_path.glob(".*.tmp"))


def test_no_force_write_never_deletes_an_existing_destination(tmp_path: Path) -> None:
    output = tmp_path / "sample.ogg"
    output.write_bytes(b"other process")

    with pytest.raises(FileExistsError):
        tts_to_ogg._write_output(output, b"new", force=False)

    assert output.read_bytes() == b"other process"


def test_no_force_write_never_deletes_a_replacement_after_write_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output = tmp_path / "sample.ogg"

    def fail_after_replacement(_file_descriptor: int) -> None:
        output.write_bytes(b"other process")
        raise OSError("simulated write failure")

    monkeypatch.setattr(os, "fsync", fail_after_replacement)

    with pytest.raises(OSError, match="simulated write failure"):
        tts_to_ogg._write_output(output, b"new", force=False)

    assert output.read_bytes() == b"other process"
    assert not tuple(tmp_path.glob(".*.tmp"))


def test_cli_maps_racing_destination_to_overwrite_exit_code(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def render(_text: str) -> bytes:
        await asyncio.sleep(0)
        return b"ogg"

    def racing_write(_path: Path, _data: bytes, *, force: bool) -> None:
        assert not force
        raise FileExistsError

    monkeypatch.setattr(tts_to_ogg, "_read_stdin", lambda: "text")
    monkeypatch.setattr(tts_to_ogg, "_render", render)
    monkeypatch.setattr(tts_to_ogg, "_write_output", racing_write)

    assert tts_to_ogg.main([str(tmp_path / "sample.ogg")]) == 2
    assert "already exists" in capsys.readouterr().err


def test_cli_maps_render_failure_without_source_text(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def render(text: str) -> bytes:
        await asyncio.sleep(0)
        raise RuntimeError(text)

    monkeypatch.setattr(tts_to_ogg, "_read_stdin", lambda: "private phrase")
    monkeypatch.setattr(tts_to_ogg, "_render", render)
    output = tmp_path / "sample.ogg"

    assert tts_to_ogg.main([str(output)]) == 1
    assert not output.exists()
    assert "private phrase" not in capsys.readouterr().err


def test_cli_interrupt_exit_code(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def interrupt(coro: object) -> bytes:
        cast(Coroutine[Any, Any, object], coro).close()
        raise KeyboardInterrupt

    monkeypatch.setattr(tts_to_ogg, "_read_stdin", lambda: "text")
    monkeypatch.setattr(asyncio, "run", interrupt)
    assert tts_to_ogg.main([str(tmp_path / "sample.ogg")]) == 130

    def interrupt_stdin() -> str:
        raise KeyboardInterrupt

    monkeypatch.setattr(tts_to_ogg, "_read_stdin", interrupt_stdin)
    assert tts_to_ogg.main([str(tmp_path / "sample.ogg")]) == 130
