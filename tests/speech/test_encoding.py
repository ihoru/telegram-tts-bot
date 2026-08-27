import subprocess

import pytest

from telegram_tts_bot.speech.encoding import FfmpegVoiceEncoder
from telegram_tts_bot.speech.errors import EncodingError
from telegram_tts_bot.speech.types import VoiceAudio, WavAudio


def test_ffmpeg_encoder_uses_production_voice_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    observed: dict[str, object] = {}

    def fake_run(command: tuple[str, ...], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        observed["command"] = command
        observed.update(kwargs)
        return subprocess.CompletedProcess(command, 0, stdout=b"ogg", stderr=b"")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = FfmpegVoiceEncoder().encode(WavAudio(b"wav"))

    assert result == VoiceAudio(b"ogg")
    assert observed["input"] == b"wav"
    command = observed["command"]
    assert isinstance(command, tuple)
    assert command[command.index("-ac") : command.index("-ac") + 2] == ("-ac", "1")
    assert command[command.index("-ar") : command.index("-ar") + 2] == ("-ar", "48000")
    assert "libopus" in command
    assert "32k" in command
    assert command[command.index("-threads") : command.index("-threads") + 2] == ("-threads", "1")


@pytest.mark.parametrize("stdout", [b"", b"partial"])
def test_ffmpeg_encoder_maps_process_failure(
    monkeypatch: pytest.MonkeyPatch,
    stdout: bytes,
) -> None:
    def fake_run(command: tuple[str, ...], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(command, 7, stdout=stdout, stderr=b"details")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(EncodingError, match="exit code 7"):
        FfmpegVoiceEncoder().encode(WavAudio(b"wav"))


def test_ffmpeg_encoder_maps_start_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(command: tuple[str, ...], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        raise OSError("secret source text")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(EncodingError, match="could not be started") as captured:
        FfmpegVoiceEncoder().encode(WavAudio(b"private"))
    assert "private" not in str(captured.value)


def test_ffmpeg_availability_check(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.which", lambda executable: None)
    with pytest.raises(EncodingError, match="unavailable"):
        FfmpegVoiceEncoder().verify_available()
