"""Render UTF-8 stdin into a production-identical OGG/Opus file."""

import argparse
import asyncio
import os
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

from telegram_tts_bot.speech import VoiceRenderError, create_voice_renderer


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tts-to-ogg",
        description="Render UTF-8 text from stdin into an OGG/Opus voice note",
    )
    parser.add_argument("file", type=Path, metavar="FILE")
    parser.add_argument("--force", action="store_true", help="replace an existing FILE")
    return parser


def _read_stdin() -> str:
    try:
        text = sys.stdin.buffer.read().decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise ValueError("stdin must be valid UTF-8") from error
    if not text.strip():
        raise ValueError("stdin must contain non-whitespace text")
    return text


def _validate_destination(path: Path, *, force: bool) -> Path:
    resolved = path.resolve()
    if not resolved.parent.is_dir():
        raise ValueError("output parent directory does not exist")
    if resolved.exists() and not force:
        raise ValueError("output file already exists; pass --force to replace it")
    if resolved.exists() and not resolved.is_file():
        raise ValueError("output path is not a regular file")
    return resolved


def _model_paths() -> tuple[Path, Path]:
    model_path = Path(
        os.environ.get("PIPER_MODEL_PATH", ".models/piper/ru_RU-denis-medium.onnx")
    ).resolve()
    config_path = Path(
        os.environ.get(
            "PIPER_CONFIG_PATH",
            ".models/piper/ru_RU-denis-medium.onnx.json",
        )
    ).resolve()
    return model_path, config_path


def _write_output(path: Path, data: bytes, *, force: bool) -> None:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(data)
            temporary.flush()
            os.fsync(temporary.fileno())
        if force:
            temporary_path.replace(path)
        else:
            # Linking is an atomic create-if-absent operation. Unlike cleaning up a
            # directly opened destination after a write failure, it can never unlink a
            # replacement installed concurrently by another process.
            os.link(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


async def _render(text: str) -> bytes:
    model_path, config_path = _model_paths()
    renderer = create_voice_renderer(model_path, config_path, max_workers=1)
    try:
        return (await renderer.render(text)).data
    finally:
        await renderer.close()


def main(argv: Sequence[str] | None = None) -> int:
    """Run the stdin renderer with stable shell-friendly exit codes."""
    args = _parser().parse_args(argv)
    try:
        text = _read_stdin()
        destination = _validate_destination(args.file, force=args.force)
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError) as error:
        print(f"tts-to-ogg: {error}", file=sys.stderr)
        return 2

    try:
        data = asyncio.run(_render(text))
        _write_output(destination, data, force=args.force)
    except KeyboardInterrupt:
        return 130
    except FileExistsError:
        print("tts-to-ogg: output file already exists; pass --force to replace it", file=sys.stderr)
        return 2
    except (OSError, VoiceRenderError, RuntimeError) as error:
        print(f"tts-to-ogg: rendering failed ({type(error).__name__})", file=sys.stderr)
        return 1

    print(destination)
    return 0
