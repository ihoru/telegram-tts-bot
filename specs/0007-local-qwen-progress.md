---
id: "0007"
title: Visible local Qwen provisioning and render progress
status: accepted
created: 2026-08-28
updated: 2026-08-28
supersedes: null
---

# SPEC-0007: Visible local Qwen provisioning and render progress

## Summary

Make slow local Qwen operations visibly advance without exposing source text. The model
provisioner reports per-file byte progress, and `tts-to-ogg` reports model loading and
ordered long-text chunk progress on stderr while preserving its existing stdout and
output-file contracts.

## Context

The pinned Qwen snapshot is about 2.5 GB, but the provisioner currently remains silent
until all eleven files have downloaded and verified. Qwen synthesis partitions long
input into lossless 500-character chunks, but the CLI emits no status between startup
and final output. A 1,304-character input therefore appears stalled during three slow,
sequential autoregressive generations.

Executing the provisioner as `python -m telegram_tts_bot.speech.qwen_model` also emits a
`runpy` warning because importing the parent `speech` package eagerly imports the target
module before Python executes it.

## Goals

- Show the current file, downloaded bytes, total bytes when known, and percentage while
  provisioning a missing Qwen snapshot.
- Format byte counts with binary size units and make Ctrl+C cancel promptly and cleanly.
- Show model-load and per-chunk synthesis progress for Qwen CLI renders.
- Remove the provisioner's eager-import `runpy` warning.
- Keep every progress message free of input text and model URLs.

## Non-goals

- Faster inference, FlashAttention installation, streaming partial Telegram audio,
  parallel chunk inference, changing the 500-character chunk ceiling, or changing the
  4,096-character input contract.
- Suppressing all upstream warnings or claiming that optional SoX and FlashAttention
  warnings are synthesis failures.

## User-visible behavior

`python -m telegram_tts_bot.speech.qwen_model` writes one updating stderr progress line
for each required file that must be downloaded. It includes the file ordinal and name,
human-readable downloaded and response sizes using B, KiB, MiB, or GiB, and an integer
percentage when the response size is available.
Completion retains the resolved model path as the only stdout line. Reusing a verified
snapshot does not fabricate download progress.

Ctrl+C closes the active response, removes partial staging data, prints one concise
content-free cancellation line, and exits with status 130 without a traceback. Network
reads are at most 64 KiB so cancellation and progress do not wait on a 1 MiB read.

For a Qwen voice, `tts-to-ogg` writes content-free stderr status before and after model
loading, before each non-whitespace chunk, and after final waveform assembly. Chunk
status includes only the one-based chunk ordinal and total. The resolved output path
remains the only stdout line on success, and no partial output file is published.

Silero CLI output is unchanged. Library callers do not receive unsolicited direct
prints; Qwen progress is emitted through the adapter's dedicated logger, which the CLI
enables locally.

## Design and interfaces

The provisioner accepts an optional progress callback. Network and checksum behavior,
staging cleanup, immutable asset manifest, and atomic installation stay unchanged. The
module entrypoint supplies a terminal reporter; tests and programmatic callers may omit
it.

The Qwen adapter lazily imports the model verifier so importing the `speech` package no
longer preloads the provisioner module. It emits structured, content-free progress
records through `telegram_tts_bot.speech.qwen`. `tts-to-ogg` installs and removes a
dedicated stderr handler for that logger around one render, without changing root
logging or third-party logger levels.

## Configuration, security, and privacy

No configuration is added. Progress contains no input text, chunk text, URL, secret,
absolute model path, or Telegram data. Existing offline loading and checksum validation
remain mandatory.

## Failure cases

An unknown response size reports a human-readable downloaded size without a percentage.
Interrupted downloads exit 130; failed downloads retain exit 1. Both remove staging.
Failed
loads or chunks retain content-free synthesis errors and publish no destination file.

## Acceptance criteria

- The module entrypoint runs without the eager-import `RuntimeWarning`.
- A synthetic download test observes monotonic 64 KiB reads, human-readable size
  progress, and a final 100 percent.
- A simulated Ctrl+C returns 130 without a traceback and leaves no partial snapshot.
- A multi-chunk Qwen CLI test observes load and every chunk ordinal on stderr, with no
  input text, while stdout still contains only the final path.
- The existing lossless long-text, offline, checksum, atomic-write, and privacy tests
  continue to pass.
- Locked Ruff, format, mypy, and pytest checks pass.

## Test plan

- Run the module entrypoint help command in a subprocess and assert clean stderr.
- Exercise the provisioner with an in-memory response carrying a content length.
- Interrupt a synthetic download and assert exit code, message, and staging cleanup.
- Exercise more than 1,000 characters through the fake Qwen model and CLI logger.
- Run the complete locked project test suite.

## Delivery and rollback

Ship with SPEC-0005 and SPEC-0006. Rollback removes the additive progress wiring and
lazy import; model assets, generated audio, configuration, and persistence are
unchanged.

## Alternatives

Printing directly from the adapter would pollute bot and library consumers. Redirecting
all process output would hide useful failures and is process-global. Parallel generation
was rejected because the accepted one-render GPU capacity does not prove it safe.

Official three-chunk batch generation was measured separately on the reference RTX 2000
Ada: 43.95 seconds and 5.12 GiB reserved VRAM versus 100.47 seconds and 3.45 GiB for
sequential generation. It changed every seeded waveform and shortened combined audio
from 110.56 to 93.84 seconds, so it requires a listening decision rather than entering
this progress-only change.

## Open questions

None.
