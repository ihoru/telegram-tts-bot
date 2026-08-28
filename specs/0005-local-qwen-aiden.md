---
id: "0005"
title: Local Qwen Aiden and Serena with Silero fallback voices
status: superseded
created: 2026-08-28
updated: 2026-08-28
supersedes: "0004"
superseded_by: "0008"
---

# SPEC-0005: Local Qwen Aiden and Serena with Silero fallback voices

## Summary

Add the local Qwen3-TTS 12 Hz 0.6B CustomVoice model with Aiden as the default and
Serena as a selectable alternative. Retain the three accepted Silero speakers. One
`TTS_VOICE` setting chooses the provider and voice for the whole process; Telegram gains
no runtime selector and speech remains local and non-persistent.

SPEC-0003's record-voice activity and the existing Telegram, localization, admission,
OGG/Opus, and privacy-safe failure contracts remain in force.

## Goals

- Make `aiden` the default and offer `serena`, `kseniya`, `xenia`, and `baya`.
- Preserve mixed Russian and English text unchanged for Qwen Auto-language synthesis.
- Load the immutable Qwen snapshot from a verified, read-only local directory.
- Keep the existing engine-neutral synthesizer and renderer seams.
- Publish an accurate bilingual privacy policy for the two local providers.

## Non-goals

- Vivian as a production configuration value.
- Per-user selection, persistence, cloud TTS, runtime downloads, or automatic fallback.
- CPU Qwen support, FlashAttention, voice cloning, style instructions, or model weights
  committed to Git or baked into the image.

## User-visible behavior

`TTS_VOICE` accepts `aiden`, `serena`, `kseniya`, `xenia`, or `baya` and defaults to
`aiden`.
Qwen receives the original input with `language="Auto"`; it does not apply Silero's
Russian transliteration. Silero behavior remains unchanged when one of its speakers is
selected. Every successful request still returns one mono 48 kHz OGG/Opus voice note.

Qwen partitions long text losslessly into ordered chunks of at most 500 Unicode
characters, preferring sentence or whitespace boundaries. It concatenates native 24 kHz
PCM before the existing single FFmpeg encode, preserving the 4,096-character Telegram
contract.

## Design and interfaces

The pinned model is `Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice` at revision
`85e237c12c027371202489a0ec509ded67b5e4b5`. An explicit provisioner downloads the
eleven required files into staging, verifies a checked-in filename/checksum allowlist,
and atomically installs the complete directory. Runtime verifies the same manifest
before importing Qwen, uses local-only/offline loading, and never accesses the network.

The adapter loads once on `cuda:0` with `torch.bfloat16`, validates CUDA and the selected
Qwen speaker, and serializes inference with a lock. Each whole message resets PyTorch CPU and
CUDA seeds to `20260828`, then calls `generate_custom_voice` for each chunk with
`language="Auto"`, the configured `speaker="Aiden"` or `speaker="Serena"`,
`instruct=""`, and `max_new_tokens=2048`.
Sampling defaults otherwise remain upstream defaults. Finite non-empty one-dimensional
output is clipped and converted into mono PCM16 WAV data at the returned 24 kHz rate.

The Qwen import environment sets `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`,
`HF_HUB_DISABLE_TELEMETRY=1`, `DO_NOT_TRACK=1`, and `ORT_DISABLE_TELEMETRY=1` before
third-party imports. Errors expose only stable failure classes and no source text.

The project remains on Python 3.14. The exact dependency graph must resolve, import, and
complete real CUDA inference on Python 3.14 before delivery; failure is a blocker rather
than an implicit Python-version change.

## Configuration and capacity

- `QWEN_MODEL_PATH`: Qwen snapshot directory, locally defaulting to
  `.models/qwen3-tts-12hz-0.6b-customvoice` and in the image to `/models/qwen3-tts-12hz-0.6b-customvoice`.
- `SILERO_MODEL_PATH`: unchanged optional Silero model path.
- `TTS_VOICE`: defaults to `aiden`; accepts the five exact identifiers above.
- `TTS_MAX_CONCURRENCY`: defaults to 1. Qwen voices reject any other value; Silero may be
  raised after capacity testing and retains the documented two-render option.
- Other token, per-user, and logging configuration is unchanged.

The supported Qwen baseline is one NVIDIA GPU with 8 GiB VRAM, at least 8 GiB host RAM,
and one render. A real 500-character Aiden render used 3,160 MiB reserved VRAM and about
2,673 MiB process RSS. The image contains the CUDA runtime dependencies and Silero
weight, but not the Qwen snapshot; operators mount the verified Qwen directory read-only
and expose the selected GPU as `cuda:0`.

## Licensing, privacy, and failure cases

Qwen code and the pinned weights are attributed under Apache-2.0. Silero remains a
separately licensed CC BY-NC-SA 4.0 component, so its redistribution and use constraints
remain explicit. The privacy policy names Qwen3-TTS or Silero as local processors and
removes obsolete Piper and Russian-only claims.

A missing file, checksum mismatch, offline load failure, unavailable CUDA/BF16 device,
invalid waveform, or inference failure aborts startup or the complete render with a
content-free error. No partial audio is returned. Selecting a Qwen voice never falls
back to CPU or Silero.

## Acceptance criteria

- All five configuration values select the intended provider; Aiden is the default.
- The accepted mixed-language Aiden fixture is byte-identical at SHA-256
  `7c1dc7c820c01125d3898474a4b164146f86254d3cc98831b5486560c975793d`.
- Real Python 3.14 CUDA inference succeeds with the pinned package and model revisions.
- Real mixed-language and 4,096-character renders produce valid final Opus audio.
- Unit tests prove manifest-before-import verification, exact generation arguments,
  chunk ordering, seed behavior, serialization, audio validation, offline loading,
  provider selection, configuration, and privacy-safe failures.
- The runtime image is non-root, contains no Qwen weight, accepts a read-only model mount,
  and retains a working CPU Silero override.
- Locked Ruff, format, mypy, pytest, provisioning, container, and privacy-site checks pass.

## Delivery and rollback

Ship one CUDA-capable image with Aiden defaults. Serena uses the same verified model
snapshot. A Silero deployment sets a Silero voice and needs no GPU. Rollback deploys the
prior immutable Silero image; there is no data migration or persistent state.

## Open questions

None.
