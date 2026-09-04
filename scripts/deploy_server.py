#!/usr/bin/python3
"""Root-owned forced SSH command. Requires only the server's Python 3 stdlib."""

import fcntl
import json
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

CONTAINER = "telegram-tts-bot"
PREVIOUS = f"{CONTAINER}-previous"
IMAGE = "ghcr.io/ihoru/telegram-tts-bot"
CONFIG = Path("/etc/telegram-tts-bot/deploy.json")
LOCK = Path("/run/telegram-tts-bot-deploy.lock")


class DeploymentError(Exception):
    """An operational failure safe to report without container output."""


def image_for_command(command: str) -> str:
    if not re.fullmatch(r"deploy sha256:[0-9a-f]{64}", command):
        raise DeploymentError("Expected: deploy sha256:<64 lowercase hex characters>")
    return f"{IMAGE}@{command.removeprefix('deploy ')}"


def docker(*arguments: str) -> str:
    result = subprocess.run(
        ["/usr/bin/docker", *arguments], capture_output=True, text=True, check=False
    )
    if result.returncode:
        # Docker output can contain environment or application details.
        raise DeploymentError(f"Docker {arguments[0]} failed; inspect the server locally.")
    if arguments[0] == "logs":
        return result.stdout + result.stderr
    return result.stdout.strip()


def exists(name: str) -> bool:
    return (
        name
        in docker(
            "container", "ls", "--all", "--filter", f"name=^/{name}$", "--format", "{{.Names}}"
        ).splitlines()
    )


def running_without_restarts(name: str) -> bool:
    return docker("inspect", "--format", "{{.State.Running}} {{.RestartCount}}", name) == ("true 0")


def runtime_arguments(config_path: Path) -> list[str]:
    config = json.loads(config_path.read_text())
    env_file = Path(config["env_file"])
    if not env_file.is_absolute() or not env_file.is_file():
        raise DeploymentError("env_file must name an existing absolute file.")
    arguments = ["--env-file", str(env_file)]
    if config["runtime"] == "qwen":
        model_directory = Path(config["model_directory"])
        if not model_directory.is_absolute() or not model_directory.is_dir():
            raise DeploymentError("model_directory must name an existing absolute directory.")
        arguments.extend([
            "--gpus",
            config.get("gpu", "device=0"),
            "--mount",
            f"type=bind,source={model_directory},"
            "target=/models/qwen3-tts-12hz-0.6b-customvoice,readonly",
        ])
    elif config["runtime"] != "silero":
        raise DeploymentError("runtime must be silero or qwen.")
    return arguments


def wait_for_startup() -> None:
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        if not running_without_restarts(CONTAINER):
            raise DeploymentError("New container exited or restarted during startup.")
        if "bot_polling_started" in docker("logs", CONTAINER):
            time.sleep(10)
            if running_without_restarts(CONTAINER):
                return
            raise DeploymentError("New container failed the startup stability check.")
        time.sleep(2)
    raise DeploymentError("New container did not report polling startup within 600 seconds.")


def remove_current() -> None:
    if exists(CONTAINER):
        docker("stop", "--timeout", "600", CONTAINER)
        docker("rm", CONTAINER)


def deploy(image: str, arguments: list[str]) -> None:
    had_current = exists(CONTAINER)
    if exists(PREVIOUS):
        if not had_current:
            raise DeploymentError("Only the previous container exists; restore it locally first.")
        if docker("inspect", "--format", "{{.State.Running}}", PREVIOUS) != "false":
            raise DeploymentError("Previous container is running; resolve this locally first.")
    docker("pull", image)
    if exists(PREVIOUS):
        docker("rm", PREVIOUS)
    try:
        if had_current:
            docker("stop", "--timeout", "600", CONTAINER)
            docker("rename", CONTAINER, PREVIOUS)
        docker(
            "run",
            "--detach",
            "--name",
            CONTAINER,
            "--init",
            "--restart",
            "unless-stopped",
            "--stop-timeout",
            "600",
            "--log-driver",
            "local",
            "--log-opt",
            "max-size=10m",
            "--log-opt",
            "max-file=3",
            *arguments,
            image,
        )
        wait_for_startup()
    except BaseException:
        # Avoid a second termination interrupting the recovery attempt.
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        if had_current:
            if exists(PREVIOUS):
                remove_current()
                docker("rename", PREVIOUS, CONTAINER)
            docker("start", CONTAINER)
            print("Restored previous container; verify its operation on the server.", flush=True)
        else:
            remove_current()
        raise
    print(f"Deployed {image}", flush=True)


def terminated(signum: int, _frame: object) -> None:
    raise DeploymentError(f"Deployment interrupted by signal {signum}.")


def main() -> int:
    try:
        if len(sys.argv) != 2:
            raise DeploymentError("Supply the original SSH command as one argument.")
        image = image_for_command(sys.argv[1])
        signal.signal(signal.SIGHUP, signal.SIG_IGN)
        signal.signal(signal.SIGTERM, terminated)
        signal.signal(signal.SIGINT, terminated)
        with LOCK.open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            deploy(image, runtime_arguments(CONFIG))
    except DeploymentError as error:
        print(str(error), file=sys.stderr)
        return 1
    except (OSError, ValueError, KeyError, TypeError):
        print("Deployment configuration, lock, or system operation failed.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
