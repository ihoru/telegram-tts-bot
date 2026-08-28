import asyncio
import importlib
import io
import logging
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
    async def render(text: str, voice: str | None = None) -> tuple[bytes, float]:
        await asyncio.sleep(0)
        assert text == "a" * 5000
        assert voice is None
        return b"ogg", 1.23456

    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setenv("QWEN_MODEL_PATH", str(tmp_path / "qwen"))
    monkeypatch.setattr(tts_to_ogg, "_read_stdin", lambda: "a" * 5000)
    monkeypatch.setattr(tts_to_ogg, "_render", render)
    output = tmp_path / "sample.ogg"

    assert tts_to_ogg.main([str(output)]) == 0
    assert output.read_bytes() == b"ogg"
    captured = capsys.readouterr()
    assert captured.out.strip() == str(output.resolve())
    assert captured.err.strip() == "tts-to-ogg: rendered in 1.235 seconds"


def test_cli_writes_binary_ogg_to_stdout_without_a_filename(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def render(text: str, voice: str | None = None) -> tuple[bytes, float]:
        await asyncio.sleep(0)
        assert text == "play this"
        assert voice == "serena"
        return b"OggS-binary-audio", 2.0

    monkeypatch.setenv("TTS_VOICE", "baya")
    monkeypatch.setattr(tts_to_ogg, "_read_stdin", lambda: "play this")
    monkeypatch.setattr(tts_to_ogg, "_render", render)

    assert tts_to_ogg.main(["--voice", "serena"]) == 0
    captured = capsys.readouterr()
    assert captured.out == "OggS-binary-audio"
    assert captured.err.strip() == "tts-to-ogg: rendered in 2.000 seconds"


def test_cli_rejects_force_without_a_filename_before_reading_stdin(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        tts_to_ogg,
        "_read_stdin",
        lambda: (_ for _ in ()).throw(AssertionError("stdin must not be read")),
    )

    assert tts_to_ogg.main(["--force"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "--force requires FILE" in captured.err


def test_cli_forwards_only_qwen_progress_to_stderr(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def render(_text: str, _voice: str | None = None) -> tuple[bytes, float]:
        await asyncio.sleep(0)
        logging.getLogger("telegram_tts_bot.speech.qwen").info("generating Qwen chunk 1/3")
        logging.getLogger("unrelated").warning("unrelated warning")
        return b"ogg", 3.5

    monkeypatch.setattr(tts_to_ogg, "_read_stdin", lambda: "private text")
    monkeypatch.setattr(tts_to_ogg, "_render", render)
    output = tmp_path / "sample.ogg"

    assert tts_to_ogg.main([str(output)]) == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == str(output.resolve())
    assert captured.err.splitlines() == [
        "tts-to-ogg: generating Qwen chunk 1/3",
        "tts-to-ogg: rendered in 3.500 seconds",
    ]
    assert "private text" not in captured.err


def test_cli_validates_path_before_rendering(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    rendered = False

    async def render(text: str, voice: str | None = None) -> tuple[bytes, float]:
        nonlocal rendered
        await asyncio.sleep(0)
        assert voice is None
        rendered = True
        return b"ogg", 1.0

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

    clock_values = iter([10.0, 11.25])

    def clock() -> float:
        calls.append("clock")
        return next(clock_values)

    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setenv("QWEN_MODEL_PATH", str(tmp_path / "qwen"))
    monkeypatch.setenv("SILERO_MODEL_PATH", str(tmp_path / "model.pt"))
    monkeypatch.setenv("TTS_VOICE", "xenia")
    monkeypatch.setattr(tts_to_ogg, "create_voice_renderer", renderer_factory)
    monkeypatch.setattr(tts_to_ogg, "perf_counter", clock)

    assert asyncio.run(tts_to_ogg._render("private text")) == (b"ogg", 1.25)
    assert calls == [
        {
            "qwen_model_path": (tmp_path / "qwen").resolve(),
            "silero_model_path": (tmp_path / "model.pt").resolve(),
            "voice": "xenia",
            "max_workers": 1,
        },
        "clock",
        "private text",
        "clock",
        "closed",
    ]


def test_render_voice_option_overrides_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    selected_voices: list[str] = []

    class Renderer:
        async def render(self, _text: str) -> object:
            await asyncio.sleep(0)
            return SimpleNamespace(data=b"ogg")

        async def close(self) -> None:
            await asyncio.sleep(0)

    def renderer_factory(**kwargs: object) -> Renderer:
        selected_voices.append(cast(str, kwargs["voice"]))
        return Renderer()

    monkeypatch.setenv("TTS_VOICE", "baya")
    monkeypatch.setenv("QWEN_MODEL_PATH", str(tmp_path / "qwen"))
    monkeypatch.setattr(tts_to_ogg, "create_voice_renderer", renderer_factory)

    assert asyncio.run(tts_to_ogg._render("text", "serena"))[0] == b"ogg"
    assert selected_voices == ["serena"]


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
    assert "aiden, serena, kseniya, xenia, baya" in capsys.readouterr().err


def test_cli_voice_option_rejects_unsupported_value_even_when_environment_is_valid(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("TTS_VOICE", "baya")
    monkeypatch.setattr(tts_to_ogg, "_read_stdin", lambda: "text")
    output = tmp_path / "sample.ogg"

    assert tts_to_ogg.main(["--voice", "denis", str(output)]) == 2
    assert not output.exists()
    assert "aiden, serena, kseniya, xenia, baya" in capsys.readouterr().err


def test_cli_refuses_overwrite_and_force_replaces_atomically(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    async def render(text: str, _voice: str | None = None) -> tuple[bytes, float]:
        await asyncio.sleep(0)
        return b"new", 1.0

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
    async def render(_text: str, _voice: str | None = None) -> tuple[bytes, float]:
        await asyncio.sleep(0)
        return b"ogg", 1.0

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
    async def render(text: str, _voice: str | None = None) -> tuple[bytes, float]:
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


def test_cli_loads_repository_environment_before_reading_input(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    events: list[str] = []

    async def render(_text: str, _voice: str | None = None) -> tuple[bytes, float]:
        await asyncio.sleep(0)
        return b"OggS", 1.0

    def read_stdin() -> str:
        events.append("stdin")
        return "text"

    monkeypatch.setattr(
        tts_to_ogg,
        "load_repository_environment",
        lambda: events.append("environment"),
    )
    monkeypatch.setattr(
        tts_to_ogg,
        "_read_stdin",
        read_stdin,
    )
    monkeypatch.setattr(tts_to_ogg, "_render", render)

    assert tts_to_ogg.main([]) == 0
    assert events == ["environment", "stdin"]
    assert capsys.readouterr().out == "OggS"
