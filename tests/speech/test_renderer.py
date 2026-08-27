import asyncio
import threading

import pytest

from telegram_tts_bot.speech import InvalidTextError, VoiceAudio, VoiceRenderer, WavAudio


class RecordingSynthesizer:
    def __init__(self) -> None:
        self.text: str | None = None
        self.thread_id: int | None = None

    def synthesize(self, text: str, /) -> WavAudio:
        self.text = text
        self.thread_id = threading.get_ident()
        return WavAudio(b"wav")


class RecordingEncoder:
    def __init__(self) -> None:
        self.audio: WavAudio | None = None

    def encode(self, audio: WavAudio, /) -> VoiceAudio:
        self.audio = audio
        return VoiceAudio(b"ogg")


async def test_renderer_runs_complete_pipeline_on_worker_thread() -> None:
    synthesizer = RecordingSynthesizer()
    encoder = RecordingEncoder()
    renderer = VoiceRenderer(synthesizer, encoder, max_workers=1)

    result = await renderer.render("  точный текст  ")

    assert result == VoiceAudio(b"ogg")
    assert synthesizer.text == "  точный текст  "
    assert synthesizer.thread_id != threading.get_ident()
    assert encoder.audio == WavAudio(b"wav")
    await renderer.close()


async def test_renderer_rejects_blank_text_and_closed_renderer() -> None:
    renderer = VoiceRenderer(RecordingSynthesizer(), RecordingEncoder(), max_workers=1)

    with pytest.raises(InvalidTextError, match="must not be empty"):
        await renderer.render(" \n ")

    await renderer.close()
    await renderer.close()
    with pytest.raises(RuntimeError, match="closed"):
        await renderer.render("text")


def test_renderer_rejects_invalid_worker_count() -> None:
    with pytest.raises(ValueError, match="positive"):
        VoiceRenderer(RecordingSynthesizer(), RecordingEncoder(), max_workers=0)


async def test_cancellation_waits_for_running_worker() -> None:
    started = threading.Event()
    finish = threading.Event()

    class BlockingSynthesizer:
        def synthesize(self, text: str, /) -> WavAudio:
            started.set()
            finish.wait(timeout=2)
            return WavAudio(text.encode())

    renderer = VoiceRenderer(BlockingSynthesizer(), RecordingEncoder(), max_workers=1)
    task = asyncio.create_task(renderer.render("text"))
    for _ in range(200):
        if started.is_set():
            break
        await asyncio.sleep(0.005)
    assert started.is_set()

    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()

    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    await renderer.close()
