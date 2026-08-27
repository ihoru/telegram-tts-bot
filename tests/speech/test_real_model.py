import asyncio
import os
from pathlib import Path

import pytest

from telegram_tts_bot.speech import create_voice_renderer


def _configured_model_paths() -> tuple[Path, Path]:
    model_path = Path(os.environ.get("PIPER_MODEL_PATH", ""))
    config_path = Path(os.environ.get("PIPER_CONFIG_PATH", ""))
    if not model_path.is_file() or not config_path.is_file():
        pytest.skip("pinned Piper assets are not configured")
    return model_path, config_path


@pytest.mark.integration
@pytest.mark.stress
async def test_five_shared_model_renders_complete_under_resource_limit() -> None:
    model_path, config_path = _configured_model_paths()

    renderer = create_voice_renderer(model_path, config_path, max_workers=5)
    try:
        rendered = await asyncio.gather(
            *(renderer.render("Проверка одновременного синтеза речи.") for _ in range(5))
        )
    finally:
        await renderer.close()

    assert len(rendered) == 5
    assert all(audio.data.startswith(b"OggS") for audio in rendered)
