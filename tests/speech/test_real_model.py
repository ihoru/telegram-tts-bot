import asyncio
import os
from pathlib import Path

import pytest

from telegram_tts_bot.speech import create_voice_renderer
from telegram_tts_bot.speech.qwen_model import verify_model_directory


def _configured_silero_model_path() -> Path:
    model_path = Path(os.environ.get("SILERO_MODEL_PATH", ""))
    if not model_path.is_file():
        pytest.skip("pinned Silero model is not configured")
    return model_path


def _configured_qwen_model_path() -> Path:
    model_path = Path(os.environ.get("QWEN_MODEL_PATH", ""))
    try:
        verify_model_directory(model_path)
    except OSError, ValueError:
        pytest.skip("pinned Qwen model is not configured")
    return model_path


@pytest.mark.integration
async def test_every_supported_speaker_renders_with_the_real_model() -> None:
    model_path = _configured_silero_model_path()

    for speaker in ("kseniya", "xenia", "baya"):
        renderer = create_voice_renderer(
            qwen_model_path=Path("unused"),
            silero_model_path=model_path,
            voice=speaker,
            max_workers=1,
        )
        try:
            rendered = await renderer.render("Проверка выбранного голоса.")
        finally:
            await renderer.close()

        assert rendered.data.startswith(b"OggS")


@pytest.mark.integration
async def test_maximum_length_text_renders_through_real_model_chunking() -> None:
    model_path = _configured_silero_model_path()
    text = ("Проверка длинного сообщения. " * 200)[:4096]
    assert len(text) == 4096

    renderer = create_voice_renderer(
        qwen_model_path=Path("unused"),
        silero_model_path=model_path,
        voice="kseniya",
        max_workers=1,
    )
    try:
        rendered = await renderer.render(text)
    finally:
        await renderer.close()

    assert rendered.data.startswith(b"OggS")


@pytest.mark.integration
async def test_non_cyrillic_text_renders_through_real_model_fallback() -> None:
    model_path = _configured_silero_model_path()
    renderer = create_voice_renderer(
        qwen_model_path=Path("unused"),
        silero_model_path=model_path,
        voice="kseniya",
        max_workers=1,
    )
    try:
        for text in ("Hello, world!", "1234567890", "!?.,:;", "Привет, Hello 123!"):
            rendered = await renderer.render(text)
            assert rendered.data.startswith(b"OggS")
    finally:
        await renderer.close()


@pytest.mark.integration
@pytest.mark.stress
async def test_two_shared_model_renders_complete_under_resource_limit() -> None:
    model_path = _configured_silero_model_path()

    renderer = create_voice_renderer(
        qwen_model_path=Path("unused"),
        silero_model_path=model_path,
        voice="kseniya",
        max_workers=2,
    )
    try:
        rendered = await asyncio.gather(
            *(renderer.render("Проверка одновременного синтеза речи. " * 12) for _ in range(2))
        )
    finally:
        await renderer.close()

    assert len(rendered) == 2
    assert all(audio.data.startswith(b"OggS") for audio in rendered)


@pytest.mark.integration
async def test_qwen_aiden_renders_russian_english_and_mixed_text() -> None:
    model_path = _configured_qwen_model_path()
    renderer = create_voice_renderer(
        qwen_model_path=model_path,
        silero_model_path=Path("unused"),
        voice="aiden",
        max_workers=1,
    )
    try:
        for text in (
            "Сегодня мы проверяем новый голос.",
            "Today we are checking the new voice.",
            "Сегодня проверяем deployment strategy и API rate limits.",
        ):
            rendered = await renderer.render(text)
            assert rendered.data.startswith(b"OggS")
    finally:
        await renderer.close()

    renderer = create_voice_renderer(
        qwen_model_path=model_path,
        silero_model_path=Path("unused"),
        voice="serena",
        max_workers=1,
    )
    try:
        rendered = await renderer.render("Сегодня проверяем Serena and English words.")
    finally:
        await renderer.close()
    assert rendered.data.startswith(b"OggS")


@pytest.mark.integration
async def test_qwen_maximum_length_text_renders_through_chunking() -> None:
    model_path = _configured_qwen_model_path()
    text = ("Проверяем mixed language input и API. " * 200)[:4096]
    assert len(text) == 4096
    renderer = create_voice_renderer(
        qwen_model_path=model_path,
        silero_model_path=Path("unused"),
        voice="aiden",
        max_workers=1,
    )
    try:
        rendered = await renderer.render(text)
    finally:
        await renderer.close()
    assert rendered.data.startswith(b"OggS")
