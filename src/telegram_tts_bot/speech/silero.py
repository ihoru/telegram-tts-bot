"""Silero-specific waveform synthesis adapter."""

# ruff: noqa: RUF001
# Russian fallback speech intentionally pairs Latin source keys with Cyrillic output.

from __future__ import annotations

import hashlib
import importlib
import io
import unicodedata
import wave
from collections.abc import Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

from telegram_tts_bot.speech.chunking import MAX_CHUNK_LENGTH as MAX_CHUNK_LENGTH
from telegram_tts_bot.speech.chunking import chunk_text
from telegram_tts_bot.speech.errors import SynthesisError
from telegram_tts_bot.speech.types import WavAudio

MODEL_SHA256 = "50081637b602126ee06cb3bc8a744d25651d2da149ee8864b9a379bfdd934437"
SAMPLE_RATE = 48_000
_chunk_text = chunk_text
_WARMUP_TEXT = "Короткая проверка готовности модели к синтезу."
_LATIN_TO_CYRILLIC = {
    "a": "а",
    "b": "б",
    "c": "к",
    "d": "д",
    "e": "е",
    "f": "ф",
    "g": "г",
    "h": "х",
    "i": "и",
    "j": "дж",
    "k": "к",
    "l": "л",
    "m": "м",
    "n": "н",
    "o": "о",
    "p": "п",
    "q": "к",
    "r": "р",
    "s": "с",
    "t": "т",
    "u": "у",
    "v": "в",
    "w": "в",
    "x": "кс",
    "y": "й",
    "z": "з",
}
_DIGIT_WORDS = (
    "ноль",
    "один",
    "два",
    "три",
    "четыре",
    "пять",
    "шесть",
    "семь",
    "восемь",
    "девять",
)
_PUNCTUATION_WORDS = {
    ".": "точка",
    ",": "запятая",
    "!": "восклицательный знак",
    "?": "вопросительный знак",
    ":": "двоеточие",
    ";": "точка с запятой",
    "-": "дефис",
    "–": "тире",
    "—": "тире",
    "_": "нижнее подчёркивание",
    "/": "косая черта",
    "\\": "обратная косая черта",
    "@": "собака",
    "#": "решётка",
    "%": "процент",
    "&": "амперсанд",
    "+": "плюс",
    "=": "равно",
    "*": "звёздочка",
    "^": "знак степени",
    "|": "вертикальная черта",
    "~": "тильда",
    "$": "доллар",
    "<": "меньше",
    ">": "больше",
    "(": "левая круглая скобка",
    ")": "правая круглая скобка",
    "[": "левая квадратная скобка",
    "]": "правая квадратная скобка",
    "{": "левая фигурная скобка",
    "}": "правая фигурная скобка",
    '"': "кавычка",
    "'": "апостроф",
    "`": "обратная кавычка",
    "«": "открывающая кавычка",
    "»": "закрывающая кавычка",
    "…": "многоточие",
}


class _AudioTensor(Protocol):
    @property
    def ndim(self) -> int:
        """Number of dimensions in the tensor."""

    def detach(self) -> _AudioTensor:
        """Detach the tensor from autograd."""

    def numel(self) -> int:
        """Return the number of samples."""

    def all(self) -> _AudioTensor:
        """Reduce boolean tensor elements."""

    def item(self) -> object:
        """Return one scalar value."""

    def clamp(self, minimum: float, maximum: float) -> _AudioTensor:
        """Clip samples to the normalized audio range."""

    def mul(self, value: int) -> _AudioTensor:
        """Scale normalized samples."""

    def round(self) -> _AudioTensor:
        """Round samples to integers."""

    def to(self, *, device: str, dtype: object) -> _AudioTensor:
        """Move and cast the tensor."""

    def contiguous(self) -> _AudioTensor:
        """Return contiguous storage."""

    def numpy(self) -> _NumpyArray:
        """Expose CPU tensor storage as a NumPy array."""


class _NumpyArray(Protocol):
    def astype(self, dtype: str, *, copy: bool) -> _NumpyArray:
        """Use a fixed little-endian integer representation."""

    def tobytes(self) -> bytes:
        """Return the raw contiguous bytes."""


class _SileroModel(Protocol):
    @property
    def speakers(self) -> Sequence[str]:
        """Speaker identifiers packaged in the model."""

    def to(self, device: object) -> object:
        """Move the model to one device."""

    def apply_tts(
        self,
        *,
        text: str,
        speaker: str,
        sample_rate: int,
        put_accent: bool,
        put_yo: bool,
        put_stress_homo: bool,
        put_yo_homo: bool,
        stress_single_vowel: bool,
    ) -> _AudioTensor:
        """Synthesize one waveform."""


class _PackageImporter(Protocol):
    def load_pickle(self, package: str, resource: str) -> object:
        """Load one object from a packaged model."""


class _PackageImporterFactory(Protocol):
    def __call__(self, file_or_buffer: str, /) -> _PackageImporter:
        """Open one PyTorch package."""


class _PackageNamespace(Protocol):
    PackageImporter: _PackageImporterFactory


class _TorchModule(Protocol):
    package: _PackageNamespace
    int16: object

    def set_num_threads(self, threads: int) -> None:
        """Set the process-wide PyTorch intra-operation thread count."""

    def device(self, device: str) -> object:
        """Create a device descriptor."""

    def inference_mode(self) -> AbstractContextManager[object]:
        """Disable autograd for inference."""

    def isfinite(self, tensor: _AudioTensor) -> _AudioTensor:
        """Return an element-wise finiteness mask."""


def sha256_file(path: Path) -> str:
    """Hash an asset without loading it all into memory."""
    digest = hashlib.sha256()
    try:
        with path.open("rb") as asset:
            for chunk in iter(lambda: asset.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        raise SynthesisError("Silero model is unavailable") from None
    return digest.hexdigest()


def verify_model(model_path: Path) -> None:
    """Verify the pinned model before deserializing executable package data."""
    if sha256_file(model_path) != MODEL_SHA256:
        raise SynthesisError("Silero model checksum mismatch")


def _contains_cyrillic_letter(text: str) -> bool:
    return any(
        character.isalpha() and "CYRILLIC" in unicodedata.name(character, "") for character in text
    )


def _latin_transliteration(character: str) -> str | None:
    direct = _LATIN_TO_CYRILLIC.get(character.casefold())
    if direct is not None:
        return direct
    if "LATIN" not in unicodedata.name(character, ""):
        return None
    for decomposed in unicodedata.normalize("NFKD", character):
        transliterated = _LATIN_TO_CYRILLIC.get(decomposed.casefold())
        if transliterated is not None:
            return transliterated
    return None


def _codepoint_spoken_text(character: str) -> str:
    codepoint = " ".join(_DIGIT_WORDS[int(digit)] for digit in str(ord(character)))
    return f"символ юникод {codepoint}"


def _append_verbalized_token(
    normalized_parts: list[str],
    token: str,
    *,
    source: str,
    index: int,
) -> None:
    if (
        index > 0
        and source[index - 1].isalnum()
        and normalized_parts
        and not normalized_parts[-1][-1].isspace()
    ):
        normalized_parts.append(" ")
    normalized_parts.append(token)
    if index + 1 < len(source) and source[index + 1].isalnum():
        normalized_parts.append(" ")


def _normalize_letters_and_digits(text: str) -> str:
    """Retain Cyrillic/prosody while making Latin letters and digits audible."""
    normalized_parts: list[str] = []
    for index, character in enumerate(text):
        transliterated = _latin_transliteration(character)
        if transliterated is not None:
            normalized_parts.append(transliterated)
            continue
        if "LATIN" in unicodedata.name(character, ""):
            _append_verbalized_token(
                normalized_parts,
                _codepoint_spoken_text(character),
                source=text,
                index=index,
            )
            continue
        try:
            digit = unicodedata.digit(character)
        except (TypeError, ValueError):
            digit = None
        if digit is not None:
            _append_verbalized_token(
                normalized_parts,
                _DIGIT_WORDS[digit],
                source=text,
                index=index,
            )
            continue
        normalized_parts.append(character)
    return "".join(normalized_parts)


def _fallback_spoken_text(text: str) -> str:
    """Make text rejected by Silero's Cyrillic cleaner deterministically speakable."""
    spoken_parts: list[str] = []
    transliterated_word: list[str] = []

    def flush_word() -> None:
        if transliterated_word:
            spoken_parts.append("".join(transliterated_word))
            transliterated_word.clear()

    for character in text:
        transliterated = _latin_transliteration(character)
        if transliterated is not None:
            transliterated_word.append(transliterated)
            continue

        flush_word()
        if character.isspace():
            continue
        try:
            digit = unicodedata.digit(character)
        except (TypeError, ValueError):
            digit = None
        if digit is not None:
            spoken_parts.append(_DIGIT_WORDS[digit])
            continue

        punctuation = _PUNCTUATION_WORDS.get(character)
        if punctuation is not None:
            spoken_parts.append(punctuation)
            continue

        spoken_parts.append(_codepoint_spoken_text(character))

    flush_word()
    return " ".join(spoken_parts)


def _model_spoken_text(text: str) -> str:
    normalized = _normalize_letters_and_digits(text)
    if _contains_cyrillic_letter(normalized):
        return normalized
    return _fallback_spoken_text(text)


def _pcm_from_tensor(audio: _AudioTensor, torch_module: _TorchModule) -> bytes:
    if audio.ndim != 1 or audio.numel() == 0:
        raise ValueError("invalid audio shape")
    if not bool(torch_module.isfinite(audio).all().item()):
        raise ValueError("invalid audio sample")

    pcm_samples = (
        audio.detach()
        .clamp(-1.0, 1.0)
        .mul(32_767)
        .round()
        .to(device="cpu", dtype=torch_module.int16)
        .contiguous()
        .numpy()
        .astype("<i2", copy=False)
    )
    return pcm_samples.tobytes()


def _wav_from_pcm(pcm_frames: bytes | bytearray) -> WavAudio:
    with io.BytesIO() as buffer:
        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(SAMPLE_RATE)
            wav_file.writeframes(pcm_frames)
        return WavAudio(data=buffer.getvalue())


@dataclass(slots=True)
class SileroWaveSynthesizer:
    """Adapt one loaded Silero speaker to the engine-neutral contract."""

    model: _SileroModel
    torch: _TorchModule
    speaker: str

    @classmethod
    def load(cls, model_path: Path, speaker: str) -> SileroWaveSynthesizer:
        """Verify, load, validate, and warm one local Silero model on CPU."""
        verify_model(model_path)

        try:
            torch_module = cast(_TorchModule, importlib.import_module("torch"))
            torch_module.set_num_threads(1)
            importer = torch_module.package.PackageImporter(str(model_path))
            model = cast(_SileroModel, importer.load_pickle("tts_models", "model"))
            model.to(torch_module.device("cpu"))
            if speaker not in model.speakers:
                raise ValueError("speaker is absent")

            synthesizer = cls(model=model, torch=torch_module, speaker=speaker)
            _pcm_from_tensor(synthesizer._apply_tts(_WARMUP_TEXT), torch_module)
        except Exception:
            raise SynthesisError("Silero model could not be loaded") from None
        return synthesizer

    def _apply_tts(self, text: str) -> _AudioTensor:
        with self.torch.inference_mode():
            return self.model.apply_tts(
                text=text,
                speaker=self.speaker,
                sample_rate=SAMPLE_RATE,
                put_accent=True,
                put_yo=True,
                put_stress_homo=True,
                put_yo_homo=True,
                stress_single_vowel=True,
            )

    def synthesize(self, text: str, /) -> WavAudio:
        """Create a complete in-memory 48 kHz mono PCM16 WAV file."""
        try:
            pcm_frames = bytearray()
            for chunk in _chunk_text(text):
                if not chunk.strip():
                    continue
                model_text = _model_spoken_text(chunk)
                for model_chunk in _chunk_text(model_text):
                    pcm_frames.extend(_pcm_from_tensor(self._apply_tts(model_chunk), self.torch))
            return _wav_from_pcm(pcm_frames)
        except Exception:
            raise SynthesisError("Silero synthesis failed") from None
