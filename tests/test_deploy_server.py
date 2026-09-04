import json
import subprocess
from pathlib import Path

import pytest

from scripts import deploy_server as deployment

DIGEST = "sha256:" + "a" * 64
IMAGE = f"{deployment.IMAGE}@{DIGEST}"


class FakeDocker:
    def __init__(self, fail: str = "") -> None:
        self.containers = {deployment.CONTAINER: "old"}
        self.running = {deployment.CONTAINER}
        self.calls: list[tuple[str, ...]] = []
        self.fail = fail

    def __call__(self, *arguments: str) -> str:
        self.calls.append(arguments)
        command = arguments[0]
        name = arguments[-1]
        if command == self.fail:
            self.fail = ""
            raise deployment.DeploymentError("Simulated Docker failure")
        if command == "container":
            requested = arguments[4].removeprefix("name=^/").removesuffix("$")
            return requested if requested in self.containers else ""
        if command == "inspect":
            state = "true" if name in self.running else "false"
            return f"{state} 0" if "RestartCount" in arguments[2] else state
        if command == "stop":
            self.running.discard(name)
        elif command == "rename":
            old = arguments[1]
            assert old not in self.running
            self.containers[name] = self.containers.pop(old)
        elif command == "rm":
            assert name not in self.running
            self.containers.pop(name)
        elif command == "run":
            assert not self.running, "Two bots must never poll concurrently"
            self.containers[deployment.CONTAINER] = "new"
            self.running.add(deployment.CONTAINER)
        elif command == "start":
            assert name in self.containers
            self.running.add(name)
        elif command == "logs":
            return "INFO bot_polling_started"
        return ""


@pytest.fixture
def docker(monkeypatch: pytest.MonkeyPatch) -> FakeDocker:
    fake = FakeDocker()
    monkeypatch.setattr(deployment, "docker", fake)
    monkeypatch.setattr("scripts.deploy_server.time.sleep", lambda _seconds: None)
    monkeypatch.setattr("scripts.deploy_server.signal.signal", lambda *_args: None)
    return fake


@pytest.mark.parametrize("command", ["check", "", "deploy latest", f"deploy {DIGEST}; id"])
def test_rejects_commands_outside_digest_contract(command: str) -> None:
    with pytest.raises(deployment.DeploymentError, match="Expected"):
        deployment.image_for_command(command)


def test_digest_is_restricted_to_this_repository() -> None:
    assert deployment.image_for_command(f"deploy {DIGEST}") == IMAGE


def test_deploy_preserves_previous_container_and_pulls_before_stopping(docker: FakeDocker) -> None:
    deployment.deploy(IMAGE, ["--env-file", "/server/.env"])
    assert docker.containers == {
        deployment.CONTAINER: "new",
        deployment.PREVIOUS: "old",
    }
    assert docker.running == {deployment.CONTAINER}
    commands = [call[0] for call in docker.calls]
    assert commands.index("pull") < commands.index("stop") < commands.index("run")
    assert ("stop", "--timeout", "600", deployment.CONTAINER) in docker.calls
    run = next(call for call in docker.calls if call[0] == "run")
    assert run[-3:] == ("--env-file", "/server/.env", IMAGE)


def test_pull_failure_keeps_old_container_running(docker: FakeDocker) -> None:
    docker.fail = "pull"
    with pytest.raises(deployment.DeploymentError):
        deployment.deploy(IMAGE, [])
    assert docker.containers == {deployment.CONTAINER: "old"}
    assert docker.running == {deployment.CONTAINER}
    assert not any(call[0] == "stop" for call in docker.calls)


@pytest.mark.parametrize("failure", ["stop", "rename", "run", "logs"])
def test_replacement_failure_restores_original_container(docker: FakeDocker, failure: str) -> None:
    docker.fail = failure
    with pytest.raises(deployment.DeploymentError):
        deployment.deploy(IMAGE, [])
    assert docker.containers == {deployment.CONTAINER: "old"}
    assert docker.running == {deployment.CONTAINER}


def test_restart_during_startup_restores_old_container(
    docker: FakeDocker, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(deployment, "running_without_restarts", lambda _name: False)
    with pytest.raises(deployment.DeploymentError, match="exited or restarted"):
        deployment.deploy(IMAGE, [])
    assert docker.containers == {deployment.CONTAINER: "old"}


def test_missing_current_with_backup_requires_operator_recovery(docker: FakeDocker) -> None:
    docker.containers = {deployment.PREVIOUS: "old"}
    docker.running.clear()
    with pytest.raises(deployment.DeploymentError, match="restore it locally"):
        deployment.deploy(IMAGE, [])
    assert docker.containers == {deployment.PREVIOUS: "old"}
    assert not any(call[0] == "pull" for call in docker.calls)


def test_first_deployment_failure_cleans_up_without_rollback(
    docker: FakeDocker, monkeypatch: pytest.MonkeyPatch
) -> None:
    docker.containers.clear()
    docker.running.clear()
    monkeypatch.setattr(deployment, "running_without_restarts", lambda _name: False)
    with pytest.raises(deployment.DeploymentError):
        deployment.deploy(IMAGE, [])
    assert not docker.containers
    assert not docker.running


def test_successive_deployment_replaces_stopped_backup(docker: FakeDocker) -> None:
    docker.containers[deployment.PREVIOUS] = "older"
    deployment.deploy(IMAGE, [])
    assert docker.containers[deployment.PREVIOUS] == "old"


def test_polling_marker_on_stderr_is_used_without_exposing_output(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([], 0, stdout="", stderr="INFO bot_polling_started")

    monkeypatch.setattr(subprocess, "run", run)
    assert "bot_polling_started" in deployment.docker("logs", deployment.CONTAINER)
    assert capsys.readouterr() == ("", "")


def test_qwen_configuration_preserves_model_mount_and_gpu(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.touch()
    config = tmp_path / "deploy.json"
    config.write_text(
        json.dumps({
            "runtime": "qwen",
            "env_file": str(env_file),
            "model_directory": str(tmp_path),
            "gpu": "device=1",
        })
    )
    arguments = deployment.runtime_arguments(config)
    assert arguments[:4] == ["--env-file", str(env_file), "--gpus", "device=1"]
    assert arguments[-1] == (
        f"type=bind,source={tmp_path},target=/models/qwen3-tts-12hz-0.6b-customvoice,readonly"
    )
