---
id: "0009"
title: Qwen punctuation and CLI ergonomics
status: accepted
created: 2026-08-28
updated: 2026-08-28
supersedes: null
---

# SPEC-0009: Qwen punctuation and CLI ergonomics

## Summary

Normalize Telegram-style em dashes before Qwen synthesis and make the local TTS command
convenient for voice selection, timed renders, file output, and direct playback. Both
Python entrypoints load the repository-root `.env`, and executable repository launchers
remove the need for manual environment imports.

SPEC-0003's Telegram activity, SPEC-0007's content-free Qwen progress, and SPEC-0008's
accelerated local runtime remain in force.

## Context

Qwen does not produce the intended audible pause for U+2014 em dashes commonly found in
Telegram text. The existing `tts-to-ogg` command requires a filename, takes its voice
only from `TTS_VOICE`, and does not report synthesis time independently from model load.
Local bot startup also requires manually exporting `.env` values.

## Goals

- Replace every U+2014 em dash with ASCII `-` for Qwen only.
- Add a per-invocation voice override while preserving environment and default fallback.
- Support raw OGG stdout suitable for `paplay` when no filename is supplied.
- Report successful synthesis and encoding time without model initialization.
- Load the repository `.env` automatically and provide concise `bin/` launchers.

## Non-goals

- Normalizing en dashes, minus signs, or other punctuation.
- Changing Silero text processing, Telegram validation, Qwen chunk size, audio encoding,
  provider models, or process-wide bot voice selection.
- Streaming partial model output, measuring model initialization, or loading arbitrary
  working-directory `.env` files.

## User-visible behavior

The command contract is `tts-to-ogg [--voice VOICE] [FILE] [--force]`. `--voice`
accepts `aiden`, `serena`, `kseniya`, `xenia`, or `baya`; selection precedence is the
command option, then `TTS_VOICE`, then `aiden`.

With `FILE`, the existing validation, atomic replacement, and resolved-path stdout
contract remains unchanged. Without `FILE`, success writes only complete OGG/Opus bytes
to stdout. `--force` without `FILE` is a usage error with exit status 2. Progress,
timing, and errors never share stdout with audio.

Every successful render writes `tts-to-ogg: rendered in N.NNN seconds` to stderr. The
duration covers only `VoiceRenderer.render()`, including synthesis and the single FFmpeg
encode. It excludes renderer construction, model loading and warmup, dependency checks,
renderer cleanup, and destination or stdout writes.

Both Python entrypoints optionally load `.env` from the source repository root before
reading settings. Existing process variables win. `bin/run_bot` and `bin/tts` locate and
enter that root, then execute the bot and TTS entrypoints through the locked uv project.
They preserve all arguments and stdin. The former root `run.sh` and `tts-to-ogg.sh`
launchers are removed.

## Design and interfaces

The Qwen adapter normalizes text immediately before lossless chunking, so every chunk
receives the ASCII replacement while engine-neutral renderer and Telegram interfaces
remain unchanged. Silero continues to receive its original text.

One shared environment helper passes the explicit source-root `.env` path to
`python-dotenv` with `override=False`. A missing file is a no-op. Containers and installed
packages without that source-root file continue to use the real process environment.

The CLI render helper returns the encoded bytes and monotonic elapsed render duration.
The caller publishes either an atomic file or binary stdout only after the full render
succeeds.

## Configuration, security, and privacy

No new setting or secret is introduced. `.env` remains ignored and is never printed.
The CLI option contains only a public speaker identifier; source text remains stdin-only
and absent from logs, exceptions, and process arguments.

## Failure cases

Unsupported voices and `--force` without a file exit 2 before model initialization.
Invalid stdin, destinations, configuration, rendering, interruption, and atomic cleanup
retain their existing exit codes and content-free messages. Failed renders publish no
file and no successful timing line.

## Acceptance criteria

- Qwen receives `-` for every input `—`, including across multi-chunk input; Silero text
  is unchanged.
- Voice selection follows option, environment, and default precedence.
- File mode preserves atomic output and path stdout; stream mode emits only valid OGG
  bytes on stdout and remains suitable for `paplay`.
- Successful Qwen and Silero renders report only render time on stderr to three decimal
  places, excluding model construction.
- Both entrypoints load only the repository-root `.env` without overriding the process
  environment, and both executable launchers work from outside the repository.
- Locked Ruff, format, mypy, and pytest checks pass.

## Test plan

- Unit-test Qwen normalization with single- and multi-chunk text and retain Silero input
  tests as provider-isolation coverage.
- Test CLI voice precedence, validation, file and binary output, timing boundaries,
  progress separation, force validation, failures, and interruption.
- Test environment loading for present, missing, and already-set values.
- Run both launchers against a fake `uv` to verify root selection, exact arguments, and
  stdin forwarding without loading a model.
- Run the complete locked project quality gate.

## Delivery and rollback

Ship code, documentation, dependency lock, and launchers together. Rollback restores the
previous mandatory-file CLI and root launchers; no data or model migration is required.

## Alternatives

Handler-level punctuation replacement was rejected because CLI Qwen renders need the
same correction and provider-specific behavior belongs in the adapter. Writing timing
to stdout was rejected because it would corrupt piped audio. Working-directory dotenv
search was rejected so unrelated parent configuration cannot be loaded accidentally.

## Open questions

None.
