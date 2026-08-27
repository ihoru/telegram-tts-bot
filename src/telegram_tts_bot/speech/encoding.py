"""FFmpeg OGG/Opus encoding."""

import shutil
import subprocess
from dataclasses import dataclass
from typing import Protocol

from telegram_tts_bot.speech.errors import EncodingError
from telegram_tts_bot.speech.types import VoiceAudio, WavAudio


class VoiceEncoder(Protocol):
    """Convert a waveform into a Telegram voice note."""

    def encode(self, audio: WavAudio, /) -> VoiceAudio:
        """Encode a complete waveform."""


@dataclass(frozen=True, slots=True)
class FfmpegVoiceEncoder:
    """Encode WAV bytes as mono 48 kHz OGG/Opus."""

    executable: str = "ffmpeg"

    def verify_available(self) -> None:
        """Fail before serving traffic when FFmpeg is unavailable."""
        if shutil.which(self.executable) is None:
            raise EncodingError("FFmpeg executable is unavailable")

    def encode(self, audio: WavAudio, /) -> VoiceAudio:
        """Run one bounded, non-interactive FFmpeg process."""
        command = (
            self.executable,
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-i",
            "pipe:0",
            "-ac",
            "1",
            "-ar",
            "48000",
            "-c:a",
            "libopus",
            "-b:a",
            "32k",
            "-vbr",
            "on",
            "-threads",
            "1",
            "-f",
            "ogg",
            "pipe:1",
        )
        try:
            process = subprocess.run(
                command,
                input=audio.data,
                capture_output=True,
                check=False,
            )
        except OSError as error:
            raise EncodingError("FFmpeg could not be started") from error

        if process.returncode != 0 or not process.stdout:
            raise EncodingError(f"FFmpeg failed with exit code {process.returncode}")
        return VoiceAudio(data=process.stdout)
