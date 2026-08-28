---
id: "0008"
title: Faster Qwen CUDA-graph runtime
status: accepted
created: 2026-08-28
updated: 2026-08-28
supersedes: "0005"
---

# SPEC-0008: Faster Qwen CUDA-graph runtime

## Summary

Replace the official `qwen-tts` inference distribution with
`faster-qwen3-tts==0.4.0` and its `qwen-tts-hf` compatibility dependency. Keep the
pinned Qwen model, Aiden and Serena voices, mixed-language input, chunking, local-only
processing, and all engine-neutral bot contracts unchanged.

SPEC-0003's record-voice activity, SPEC-0006's append-only audition archive, and
SPEC-0007's content-free provisioning and render progress remain in force.

## Goals

- Cut Qwen render latency materially on the supported NVIDIA GPU by using manual CUDA
  graph capture.
- Preserve the current configuration, verified model snapshot, input, output, privacy,
  and failure contracts.
- Record the accelerated runtime's deterministic Aiden output as a new dated audition
  result without replacing the official-runtime result.

## Non-goals

- Streaming partial Telegram audio, parallel or batched chunks, GGML/GGUF, quantization,
  CPU Qwen, FlashAttention, a second installed Qwen backend, or a model/voice change.

## Runtime design

The exact runtime is `faster-qwen3-tts==0.4.0`, backed by
`qwen-tts-hf==0.1.1.post1`, `transformers==5.16.1`, and the existing
`torch==2.13.0+cu130`. The official `qwen-tts` distribution is absent because both Qwen
distributions provide the same `qwen_tts` import package. Python remains 3.14.

After checksum verification and CUDA BF16 validation, the adapter loads
`FasterQwen3TTS` once on `cuda:0` with BF16, SDPA, a 2,048-token static cache, and
local-only/offline settings. Startup performs one `warmup(prefill_len=100)` to capture
the CUDA graphs. Upstream stdout emitted during loading and capture is suppressed so the
CLI retains its stdout contract.

Each message is still split losslessly into ordered chunks of at most 500 Unicode
characters. Inference remains serialized and sequential, seeds CPU and CUDA once per
message with `20260828`, and calls `generate_custom_voice` with the original chunk,
`language="Auto"`, the configured speaker, `instruct=""`, and
`max_new_tokens=2048`. The adapter validates the returned waveform and creates one
native 24 kHz PCM16 WAV before the existing single OGG/Opus render.

The accelerated algorithm is deterministic for the accepted fixture and seed but is not
byte-identical to the official inference runtime. Its output is therefore appended under
a new runtime-specific audition path. Aiden remains the bot default; the archived result
is classified as the current default implementation.

## Capacity and measured baseline

On the reference RTX 2000 Ada 8 GiB host with the exact 1,304-character, three-chunk
input used by SPEC-0007, accelerated sequential generation took 50.79 seconds and
reserved 3.40 GiB peak VRAM. The official sequential runtime took 100.47 seconds and
reserved 3.45 GiB. Accelerated startup took 10.16 seconds plus 1.22 seconds for graph
capture. The 157-character canonical fixture rendered in 5.34 seconds on the first run
and 5.12 seconds on the second.

`TTS_MAX_CONCURRENCY=1` remains mandatory for Qwen. The accepted deployment baseline is
unchanged: one NVIDIA CUDA/BF16 GPU with 8 GiB VRAM, at least 8 GiB host RAM, and one
render at a time.

## Licensing, privacy, and failure cases

Faster Qwen3-TTS is attributed under MIT and its license text is included in the image.
The Qwen inference/model code remains attributed under Apache-2.0. Model weights remain
outside Git and the image. All speech stays on the host; no new service, telemetry,
network access, persistence, or privacy-policy disclosure is introduced.

A missing or modified model, failed accelerated import/load/capture, unavailable
CUDA/BF16 device, static-cache limit, invalid waveform, or generation failure aborts
startup or the complete render with the existing content-free error. There is no
automatic fallback.

## Acceptance criteria

- Python 3.14 resolves and imports the locked accelerated stack, and real CUDA inference
  succeeds with the pinned 0.6B CustomVoice snapshot.
- The exact 1,304-character benchmark is at least 1.8 times faster than the 100.47-second
  official sequential baseline and stays below 4 GiB reserved VRAM.
- Two fresh seeded canonical Aiden renders are byte-identical; the resulting PCM16 WAV
  is appended to the audition manifest with exact runtime, hashes, date, and chronology.
- Aiden and Serena preserve the exact generation arguments, sequential chunking,
  serialization, content-free progress, local-only load, and failure contracts.
- The locked environment contains `faster-qwen3-tts` and `qwen-tts-hf`, and does not
  contain the official `qwen-tts` distribution.
- Locked Ruff, format, mypy, pytest, real-model, archive, container, privacy-site, and
  pre-commit checks pass where their prerequisites are available.

## Delivery and rollback

Ship one image containing the accelerated runtime and no Qwen weights. Rollback deploys
the previous immutable official-runtime image; the model mount, environment variables,
Telegram configuration, and persistent state need no migration.

An existing development environment that previously contained `qwen-tts` must perform
one locked `qwen-tts-hf` reinstall after synchronization because the two distributions
share the `qwen_tts` import path. Fresh environments and fresh container builds need no
special migration step.

## Open questions

None.
