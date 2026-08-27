"""Stable, content-free errors raised by the speech pipeline."""


class VoiceRenderError(Exception):
    """Base class for expected speech rendering failures."""


class InvalidTextError(VoiceRenderError):
    """The supplied text cannot be rendered."""


class SynthesisError(VoiceRenderError):
    """The waveform synthesizer failed."""


class EncodingError(VoiceRenderError):
    """The voice-note encoder failed."""
