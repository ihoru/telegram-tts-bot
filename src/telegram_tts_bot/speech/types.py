"""Engine-neutral speech data and provider contracts."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class WavAudio:
    """Complete WAV file bytes."""

    data: bytes


@dataclass(frozen=True, slots=True)
class VoiceAudio:
    """Telegram-ready voice-note bytes."""

    data: bytes
    filename: str = "voice.ogg"
    mime_type: str = "audio/ogg"


class WaveSynthesizer(Protocol):
    """Produce a complete WAV file from text."""

    def synthesize(self, text: str, /) -> WavAudio:
        """Synthesize text without retaining it."""
