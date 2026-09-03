import os
import subprocess
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _run_launcher(
    launcher: Path,
    arguments: list[str],
    *,
    tmp_path: Path,
) -> subprocess.CompletedProcess[str]:
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    fake_uv = fake_bin / "uv"
    fake_uv.write_text(
        "#!/bin/sh\n"
        "printf 'cwd=%s\\n' \"$PWD\"\n"
        "for argument do printf 'arg=%s\\n' \"$argument\"; done\n"
        "printf 'stdin='\n"
        "cat\n",
        encoding="utf-8",
    )
    fake_uv.chmod(0o755)
    environment = os.environ.copy()
    environment["PATH"] = f"{fake_bin}:{environment['PATH']}"
    return subprocess.run(
        [launcher, *arguments],
        cwd=tmp_path,
        input="private stdin",
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )


@pytest.mark.parametrize(
    ("launcher_name", "arguments", "expected_arguments"),
    [
        (
            "run_bot",
            ["argument with spaces"],
            ["run", "--active", "python", "-m", "telegram_tts_bot", "argument with spaces"],
        ),
        (
            "tts",
            ["--voice", "serena"],
            ["run", "--active", "tts-to-ogg", "--voice", "serena"],
        ),
    ],
)
def test_launcher_runs_uv_from_repository_root_and_preserves_input(
    launcher_name: str,
    arguments: list[str],
    expected_arguments: list[str],
    tmp_path: Path,
) -> None:
    launcher = REPOSITORY_ROOT / "bin" / launcher_name

    completed = _run_launcher(launcher, arguments, tmp_path=tmp_path)

    assert completed.returncode == 0
    assert os.access(launcher, os.X_OK)
    assert completed.stderr == ""
    assert completed.stdout.splitlines() == [
        f"cwd={REPOSITORY_ROOT}",
        *(f"arg={argument}" for argument in expected_arguments),
        "stdin=private stdin",
    ]
