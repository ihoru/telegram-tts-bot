"""Explicit provisioning for the pinned Piper voice assets."""

import argparse
import hashlib
import os
import tempfile
import urllib.error
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from telegram_tts_bot.speech.piper import CONFIG_SHA256, MODEL_SHA256

REVISION = "39ab474be869e9181350af6a65e4953eef67aaa0"
VOICE_ROOT = "ru/ru_RU/denis/medium"
BASE_URL = f"https://huggingface.co/rhasspy/piper-voices/resolve/{REVISION}/{VOICE_ROOT}"


@dataclass(frozen=True, slots=True)
class Asset:
    filename: str
    sha256: str

    @property
    def url(self) -> str:
        return f"{BASE_URL}/{self.filename}?download=true"


ASSETS = (
    Asset("ru_RU-denis-medium.onnx", MODEL_SHA256),
    Asset("ru_RU-denis-medium.onnx.json", CONFIG_SHA256),
)


def _download(asset: Asset, output_dir: Path) -> Path:
    destination = output_dir / asset.filename
    if destination.is_file() and _sha256(destination) == asset.sha256:
        return destination

    temporary_path: Path | None = None
    try:
        with (
            urllib.request.urlopen(asset.url, timeout=60) as response,
            tempfile.NamedTemporaryFile(
                mode="wb",
                dir=output_dir,
                prefix=f".{asset.filename}.",
                suffix=".tmp",
                delete=False,
            ) as temporary,
        ):
            temporary_path = Path(temporary.name)
            digest = hashlib.sha256()
            while chunk := response.read(1024 * 1024):
                temporary.write(chunk)
                digest.update(chunk)
            temporary.flush()
            os.fsync(temporary.fileno())
        if digest.hexdigest() != asset.sha256:
            raise ValueError(f"Checksum mismatch for {asset.filename}")
        temporary_path.replace(destination)
        return destination
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def provision(output_dir: Path) -> tuple[Path, ...]:
    """Download missing assets and return their verified paths."""
    output_dir.mkdir(parents=True, exist_ok=True)
    return tuple(_download(asset, output_dir) for asset in ASSETS)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download the pinned Vslukh Piper model")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(".models/piper"),
        help="asset directory (default: .models/piper)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Provision assets for local development or a container build."""
    args = _parser().parse_args(argv)
    try:
        paths = provision(args.output_dir.resolve())
    except (OSError, urllib.error.URLError, ValueError) as error:
        print(f"Model provisioning failed: {error}", file=__import__("sys").stderr)
        return 1
    for path in paths:
        print(path)
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through the installed module
    raise SystemExit(main())
