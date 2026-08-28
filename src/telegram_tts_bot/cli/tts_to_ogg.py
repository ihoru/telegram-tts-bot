"""Render UTF-8 stdin into a production-identical OGG/Opus file."""

import argparse
import asyncio
import logging
import os
import sys
import tempfile
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from time import perf_counter

from telegram_tts_bot.config import (
    DEFAULT_QWEN_MODEL_PATH,
    DEFAULT_SILERO_MODEL_PATH,
    DEFAULT_TTS_VOICE,
    ConfigurationError,
    validate_tts_voice,
)
from telegram_tts_bot.environment import load_repository_environment
from telegram_tts_bot.speech import VoiceRenderError, create_voice_renderer

_QWEN_LOGGER_NAME = "telegram_tts_bot.speech.qwen"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tts-to-ogg",
        description="Render UTF-8 text from stdin into an OGG/Opus voice note",
    )
    parser.add_argument("file", type=Path, nargs="?", metavar="FILE")
    parser.add_argument(
        "--voice",
        metavar="VOICE",
        help="speaker override (default: TTS_VOICE or aiden)",
    )
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


def _speech_settings(voice_override: str | None = None) -> tuple[Path, Path, str]:
    qwen_model_path = Path(
        os.environ.get("QWEN_MODEL_PATH", str(DEFAULT_QWEN_MODEL_PATH))
    ).expanduser()
    silero_model_path = Path(
        os.environ.get("SILERO_MODEL_PATH", str(DEFAULT_SILERO_MODEL_PATH))
    ).expanduser()
    voice = validate_tts_voice(voice_override or os.environ.get("TTS_VOICE", DEFAULT_TTS_VOICE))
    return qwen_model_path.resolve(), silero_model_path.resolve(), voice


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


@contextmanager
def _qwen_progress_to_stderr() -> Iterator[None]:
    logger = logging.getLogger(_QWEN_LOGGER_NAME)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("tts-to-ogg: %(message)s"))
    previous_level = logger.level
    previous_propagate = logger.propagate
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    try:
        yield
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)
        logger.propagate = previous_propagate


async def _render(text: str, voice_override: str | None = None) -> tuple[bytes, float]:
    qwen_model_path, silero_model_path, voice = _speech_settings(voice_override)
    renderer = create_voice_renderer(
        qwen_model_path=qwen_model_path,
        silero_model_path=silero_model_path,
        voice=voice,
        max_workers=1,
    )
    try:
        started_at = perf_counter()
        data = (await renderer.render(text)).data
        duration_seconds = perf_counter() - started_at
        return data, duration_seconds
    finally:
        await renderer.close()


def main(argv: Sequence[str] | None = None) -> int:
    """Run the stdin renderer with stable shell-friendly exit codes."""
    load_repository_environment()
    args = _parser().parse_args(argv)
    if args.file is None and args.force:
        print("tts-to-ogg: --force requires FILE", file=sys.stderr)
        return 2
    try:
        text = _read_stdin()
        destination = (
            _validate_destination(args.file, force=args.force) if args.file is not None else None
        )
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError) as error:
        print(f"tts-to-ogg: {error}", file=sys.stderr)
        return 2

    try:
        with _qwen_progress_to_stderr():
            data, duration_seconds = asyncio.run(_render(text, args.voice))
        if destination is None:
            sys.stdout.buffer.write(data)
            sys.stdout.buffer.flush()
        else:
            _write_output(destination, data, force=args.force)
            print(destination)
        print(
            f"tts-to-ogg: rendered in {duration_seconds:.3f} seconds",
            file=sys.stderr,
        )
    except KeyboardInterrupt:
        return 130
    except FileExistsError:
        print("tts-to-ogg: output file already exists; pass --force to replace it", file=sys.stderr)
        return 2
    except ConfigurationError as error:
        print(f"tts-to-ogg: configuration error: {error}", file=sys.stderr)
        return 2
    except (OSError, VoiceRenderError, RuntimeError) as error:
        print(f"tts-to-ogg: rendering failed ({type(error).__name__})", file=sys.stderr)
        return 1

    return 0
