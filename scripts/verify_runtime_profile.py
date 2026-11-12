"""Assertions executed inside the exact final image by verify-runtime-image.sh."""

import importlib.metadata
import importlib.util
import os
import sys
import sysconfig
from pathlib import Path

import torch  # type: ignore[import-not-found]

from telegram_tts_bot import __main__  # ruff: ignore[unused-import]
from telegram_tts_bot.cli import tts_to_ogg  # ruff: ignore[unused-import]
from telegram_tts_bot.speech import SynthesisError, create_voice_renderer

profile = sys.argv[1]
assert profile in {"cpu", "gpu"}
assert os.environ["QWEN_MODEL_PATH"] == "/models/qwen3-tts-12hz-0.6b-customvoice"
assert os.environ["SILERO_MODEL_PATH"] == "/opt/silero/v5_5_ru.pt"
assert os.environ["TTS_VOICE"] == ("xenia" if profile == "cpu" else "aiden")
assert os.environ["TTS_MAX_CONCURRENCY"] == "1"
for name in (
    "HF_HUB_OFFLINE",
    "TRANSFORMERS_OFFLINE",
    "HF_HUB_DISABLE_TELEMETRY",
    "DO_NOT_TRACK",
    "ORT_DISABLE_TELEMETRY",
):
    assert os.environ[name] == "1"
assert "PIPER_MODEL_PATH" not in os.environ
assert "PIPER_CONFIG_PATH" not in os.environ
assert importlib.util.find_spec("piper") is None
assert "telegram_tts_bot.speech.qwen" not in sys.modules
assert "soundfile" not in sys.modules

if profile == "cpu":
    assert torch.__version__ == "2.13.0+cpu"
    assert torch.version.cuda is None
    forbidden = ("nvidia", "cuda", "cudnn", "triton", "tensorrt")
    for distribution in importlib.metadata.distributions():
        name = distribution.metadata["Name"].lower().replace("_", "-")
        assert not any(part in name for part in forbidden), name
    for module in ("faster_qwen3_tts", "qwen_tts", "transformers", "torchaudio", "soundfile"):
        assert importlib.util.find_spec(module) is None, module
    libraries = (
        "cuda",
        "cudnn",
        "cublas",
        "cusparse",
        "cufft",
        "curand",
        "nccl",
        "nvrtc",
        "triton",
        "cufile",
        "cupti",
        "cusolver",
        "nvjitlink",
        "nvshmem",
    )
    for path in Path(sysconfig.get_paths()["purelib"]).rglob("*.so*"):
        assert not any(part in path.name.lower() for part in libraries), path.name
    assert not list(Path("/usr/local").glob("cuda*"))
    for voice in ("aiden", "serena"):
        try:
            create_voice_renderer(Path("unused"), Path("unused"), voice, 1)
        except SynthesisError as error:
            assert str(error) == "Qwen requires the GPU runtime dependencies"
        else:
            raise AssertionError("CPU image silently accepted a Qwen voice")
else:
    assert torch.__version__ == "2.13.0+cu130"
    assert torch.version.cuda == "13.0"
    import faster_qwen3_tts
    import torchaudio

    import telegram_tts_bot.speech.qwen  # ruff: ignore[unused-import]

    assert faster_qwen3_tts.FasterQwen3TTS is not None
    assert torchaudio.__version__ == "2.11.0+cu130"

    assert importlib.util.find_spec("faster_qwen3_tts") is not None
    assert importlib.util.find_spec("qwen_tts") is not None
    assert importlib.metadata.version("faster-qwen3-tts") == "0.4.0"
    assert importlib.metadata.version("qwen-tts-hf") == "0.1.1.post1"
    assert importlib.metadata.version("torchaudio") == "2.11.0+cu130"
    assert "qwen-tts" not in importlib.metadata.packages_distributions()["qwen_tts"]
