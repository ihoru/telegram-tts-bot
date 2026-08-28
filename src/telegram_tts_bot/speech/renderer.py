"""Reusable asynchronous speech rendering pipeline."""

import asyncio
from concurrent.futures import Future, ThreadPoolExecutor

from telegram_tts_bot.speech.encoding import VoiceEncoder
from telegram_tts_bot.speech.errors import InvalidTextError
from telegram_tts_bot.speech.types import VoiceAudio, WaveSynthesizer


async def _wait_for_thread[Result](future: Future[Result]) -> Result:
    """Bridge a thread future without relying on the loop's thread wakeup callback."""
    while not future.done():  # ruff: ignore[async-busy-wait] - thread callback wakeups fail on Python 3.14.6
        await asyncio.sleep(0.005)
    return future.result()


class VoiceRenderer:
    """Run one synchronous synthesis/encoding pipeline off the event loop."""

    def __init__(
        self,
        synthesizer: WaveSynthesizer,
        encoder: VoiceEncoder,
        *,
        max_workers: int,
    ) -> None:
        if max_workers < 1:
            raise ValueError("max_workers must be positive")
        self._synthesizer = synthesizer
        self._encoder = encoder
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="voice-render",
        )
        self._closed = False
        self._active: set[Future[VoiceAudio]] = set()

    async def render(self, text: str, /) -> VoiceAudio:
        """Render text and keep cancellation from abandoning a running worker."""
        if not text.strip():
            raise InvalidTextError("Text must not be empty")
        if self._closed:
            raise RuntimeError("VoiceRenderer is closed")

        future = self._executor.submit(self._render_sync, text)
        self._active.add(future)
        try:
            try:
                return await _wait_for_thread(future)
            except asyncio.CancelledError:
                while not future.done():  # ruff: ignore[async-busy-wait] - preserve cancellation ownership
                    await asyncio.sleep(0.005)
                raise
        finally:
            self._active.discard(future)

    def _render_sync(self, text: str) -> VoiceAudio:
        return self._encoder.encode(self._synthesizer.synthesize(text))

    async def close(self) -> None:
        """Wait for active jobs and close the dedicated executor exactly once."""
        if self._closed:
            return
        self._closed = True
        while any(not future.done() for future in self._active):  # ruff: ignore[async-busy-wait]
            await asyncio.sleep(0.005)
        self._executor.shutdown(wait=True)
