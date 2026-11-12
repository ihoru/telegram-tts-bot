from importlib.metadata import PackageNotFoundError, version

import pytest

import telegram_tts_bot


def test_package_is_installed() -> None:
    assert version("telegram-tts-bot") == "0.1.0"
    assert telegram_tts_bot.__doc__ == "Read Aloud Telegram text-to-speech bot."


def test_accelerated_qwen_runtime_is_installed_without_conflicting_distribution() -> None:
    try:
        runtime_version = version("faster-qwen3-tts")
    except PackageNotFoundError:
        pytest.skip("GPU runtime is not selected")
    assert runtime_version == "0.5.4"
    assert version("qwen-tts-hf") == "0.1.1.post1"
    with pytest.raises(PackageNotFoundError):
        version("qwen-tts")


def test_cpu_runtime_excludes_qwen_dependencies_when_selected() -> None:
    try:
        torch_version = version("torch")
    except PackageNotFoundError:
        pytest.skip("inference runtime is not selected")
    if not torch_version.endswith("+cpu"):
        pytest.skip("CPU runtime is not selected")
    for name in ("faster-qwen3-tts", "qwen-tts-hf", "transformers", "torchaudio"):
        with pytest.raises(PackageNotFoundError):
            version(name)
