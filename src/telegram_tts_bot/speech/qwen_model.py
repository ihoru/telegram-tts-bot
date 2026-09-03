"""Verified provisioning for the pinned Qwen3-TTS model directory."""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

MODEL_ID = "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"
MODEL_REVISION = "85e237c12c027371202489a0ec509ded67b5e4b5"
BASE_URL = f"https://huggingface.co/{MODEL_ID}/resolve/{MODEL_REVISION}"
DOWNLOAD_CHUNK_SIZE = 64 * 1024


@dataclass(frozen=True, slots=True)
class Asset:
    """One required immutable file in the local model snapshot."""

    filename: str
    sha256: str

    @property
    def url(self) -> str:
        return f"{BASE_URL}/{urllib.parse.quote(self.filename, safe='/')}"


ASSETS = (
    Asset("config.json", "81aca2b6fac304944d8acf345272d8a9a727d5fc2e2e66b222ab4729340c7455"),
    Asset(
        "generation_config.json",
        "f1b90b4513f3b34c62851049e2492d7b4c5940daf1276f89c82b8ef04127f3aa",
    ),
    Asset("merges.txt", "599bab54075088774b1733fde865d5bd747cbcc7a547c5bc12610e874e26f5e3"),
    Asset(
        "model.safetensors",
        "bc3c7e785eb961179c25450d1acff03f839e0002f2f3a5aeb67b5735c0fa2adb",
    ),
    Asset(
        "preprocessor_config.json",
        "efdde1022ea9d76928bf7a9cd53139138f5ba2e466e837f08f6105ab1af1c119",
    ),
    Asset(
        "speech_tokenizer/config.json",
        "ee65bb901c876664ab8707c487157aa1a6ee57c65969b28fb5ec9dc211e68167",
    ),
    Asset(
        "speech_tokenizer/configuration.json",
        "6bc26d64eb5024b4d1dab5a52371958b429256d6c9d59787f1f5294a54e0cebd",
    ),
    Asset(
        "speech_tokenizer/model.safetensors",
        "836b7b357f5ea43e889936a3709af68dfe3751881acefe4ecf0dbd30ba571258",
    ),
    Asset(
        "speech_tokenizer/preprocessor_config.json",
        "fcb3805e597e786d4067706e602f6688524640f8d3396790e2e09b5942fcbdfb",
    ),
    Asset(
        "tokenizer_config.json",
        "dc3c31c3bdaedd5016382bb3cbe07323026775ad51f5a4fb564505992ae4a670",
    ),
    Asset("vocab.json", "ca10d7e9fb3ed18575dd1e277a2579c16d108e32f27439684afa0e10b1440910"),
)


class ModelVerificationError(ValueError):
    """Raised when a local model directory is incomplete or modified."""


DownloadProgress = Callable[[int, int | None, bool], None]
ProvisionProgress = Callable[[int, int, Asset, int, int | None, bool], None]


def sha256_file(path: Path) -> str:
    """Hash one model file without loading it into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_model_directory(model_path: Path) -> None:
    """Require exactly the pinned files and checksums in one ordinary directory."""
    if not model_path.is_dir():
        raise ModelVerificationError("Qwen model directory is unavailable")

    expected = {asset.filename for asset in ASSETS}
    actual = {
        path.relative_to(model_path).as_posix()
        for path in model_path.rglob("*")
        if path.is_file() or path.is_symlink()
    }
    if actual != expected:
        raise ModelVerificationError("Qwen model file set mismatch")

    for asset in ASSETS:
        path = model_path / asset.filename
        if path.is_symlink() or not path.is_file() or sha256_file(path) != asset.sha256:
            raise ModelVerificationError("Qwen model checksum mismatch")


def _download(
    asset: Asset,
    staging: Path,
    *,
    progress: DownloadProgress | None = None,
) -> None:
    destination = staging / asset.filename
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with (
            urllib.request.urlopen(asset.url, timeout=120) as response,
            tempfile.NamedTemporaryFile(
                mode="wb",
                dir=destination.parent,
                prefix=f".{destination.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary,
        ):
            temporary_path = Path(temporary.name)
            digest = hashlib.sha256()
            raw_total = response.headers.get("Content-Length")
            total = int(raw_total) if raw_total is not None and raw_total.isdecimal() else None
            downloaded = 0
            if progress is not None:
                progress(downloaded, total, False)
            while chunk := response.read(DOWNLOAD_CHUNK_SIZE):
                temporary.write(chunk)
                digest.update(chunk)
                downloaded += len(chunk)
                if progress is not None:
                    progress(downloaded, total, False)
            temporary.flush()
            os.fsync(temporary.fileno())
        if digest.hexdigest() != asset.sha256:
            raise ModelVerificationError("Downloaded Qwen model checksum mismatch")
        temporary_path.replace(destination)
        if progress is not None:
            progress(downloaded, total, True)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def provision(
    output_dir: Path,
    *,
    progress: ProvisionProgress | None = None,
) -> Path:
    """Atomically install or reuse the complete pinned Qwen snapshot."""
    output_dir = output_dir.resolve()
    if output_dir.exists():
        verify_model_directory(output_dir)
        return output_dir

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    try:
        for index, asset in enumerate(ASSETS, start=1):
            if progress is None:
                _download(asset, staging)
            else:

                def report(
                    downloaded: int,
                    total: int | None,
                    complete: bool,
                    *,
                    current_index: int = index,
                    current_asset: Asset = asset,
                ) -> None:
                    progress(
                        current_index,
                        len(ASSETS),
                        current_asset,
                        downloaded,
                        total,
                        complete,
                    )

                _download(
                    asset,
                    staging,
                    progress=report,
                )
        verify_model_directory(staging)
        staging.rename(output_dir)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return output_dir


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download the pinned Read Aloud Qwen3-TTS model")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(".models/qwen3-tts-12hz-0.6b-customvoice"),
        help="asset directory (default: .models/qwen3-tts-12hz-0.6b-customvoice)",
    )
    return parser


def _terminal_progress(
    index: int,
    asset_count: int,
    asset: Asset,
    downloaded: int,
    total: int | None,
    complete: bool,
) -> None:
    if total is None:
        amount = _format_size(downloaded)
    else:
        percentage = min(100, downloaded * 100 // total) if total else 100
        amount = f"{_format_size(downloaded)} / {_format_size(total)} ({percentage}%)"
    print(
        f"Downloading {index}/{asset_count} {asset.filename}: {amount}",
        file=sys.stderr,
        end="\n" if complete else "\r",
        flush=True,
    )


def _format_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if value < 1024 or unit == "GiB":
            return f"{int(value)} B" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    raise AssertionError("unreachable")


def main(argv: Sequence[str] | None = None) -> int:
    """Provision the model without exposing mutable upstream paths at runtime."""
    args = _parser().parse_args(argv)
    try:
        path = provision(args.output_dir, progress=_terminal_progress)
    except KeyboardInterrupt:
        print("\nQwen model provisioning cancelled.", file=sys.stderr)
        return 130
    except (OSError, urllib.error.URLError, ModelVerificationError) as error:
        print(f"Qwen model provisioning failed: {error}", file=sys.stderr)
        return 1
    print(path)
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through the installed module
    raise SystemExit(main())
