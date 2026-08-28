import os
from pathlib import Path

import pytest

from telegram_tts_bot import environment


def test_repository_environment_loads_values_without_overriding_process(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(
        "DOTENV_NEW_VALUE=from-file\nDOTENV_EXISTING_VALUE=from-file\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(environment, "REPOSITORY_ENV_PATH", dotenv_path)
    monkeypatch.delenv("DOTENV_NEW_VALUE", raising=False)
    monkeypatch.setenv("DOTENV_EXISTING_VALUE", "from-process")

    assert environment.load_repository_environment()
    assert os.environ["DOTENV_NEW_VALUE"] == "from-file"
    assert os.environ["DOTENV_EXISTING_VALUE"] == "from-process"


def test_repository_environment_does_not_search_the_working_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    (tmp_path / ".env").write_text("DOTENV_UNRELATED=loaded\n", encoding="utf-8")
    monkeypatch.setattr(environment, "REPOSITORY_ENV_PATH", tmp_path / "missing" / ".env")
    monkeypatch.delenv("DOTENV_UNRELATED", raising=False)
    monkeypatch.chdir(tmp_path)

    assert not environment.load_repository_environment()
    assert "DOTENV_UNRELATED" not in os.environ
