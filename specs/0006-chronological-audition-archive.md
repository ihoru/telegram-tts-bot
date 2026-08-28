---
id: "0006"
title: Chronological mixed-language audition archive
status: accepted
created: 2026-08-28
updated: 2026-08-28
supersedes: null
---

# SPEC-0006: Chronological mixed-language audition archive

## Summary

Commit a small, immutable history of lossless voice auditions produced from one
synthetic mixed Russian/English prompt. The archive makes model, version, voice,
chronology, configuration, output integrity, and bot-selection decisions visible
without inspecting Git history.

## Fixture and archive contract

The `mixed-ru-en-v1` logical prompt is exactly:

> Сегодня мы обсуждали новую deployment strategy. Потом проверили API rate limits. В
> конце поговорили про user experience. The release is scheduled for Friday.

Its UTF-8 logical-text SHA-256 is
`8fda312dda13c3d3fbff95ab71a377edd0d4e077f2b3ba5d43c87b545a8f9f23`. The checked-in
text file may contain one conventional trailing newline; the renderer and validator
remove exactly that terminator. Any content change creates a new fixture version rather
than rewriting v1.

Each result is a mono PCM16 WAV captured at the provider adapter boundary before Opus
encoding. Implemented voices use the exact historical/current adapter. Rejected voices
use a disposable production-equivalent harness with the same input transformation and
inference parameters, without becoming production configuration values.

The initial archive contains one result for each of eleven audited voices:

- Piper 1.7.0: Denis, Dmitri, and Irina;
- Silero `v5_5_ru`: aidar, baya, eugene, kseniya, and xenia;
- Qwen3-TTS 12 Hz 0.6B CustomVoice: Aiden, Serena, and Vivian.

Qwen uses seed `20260828`; deterministic providers record no seed. Existing Qwen mixed
audition WAVs are retained when their bytes match the production-equivalent parameters.

## Metadata and chronology

The machine-readable manifest records fixture identity and, for every result, a stable
ID, relative WAV path, provider/runtime/model versions, immutable source revision and
model hashes, voice, seed, language and preprocessing settings, adapter/source revision,
source-model license, audio SHA-256, sample rate, channels, sample width, frames, and
duration. It contains no absolute local path.

Every entry has `auditioned_on` in `YYYY-MM-DD`, a timezone-aware `rendered_at`, a current
classification, and append-only dated `decision_history` events with relevant spec or
commit references. A human-readable README presents the same sessions in chronological
order. Backfilled canonical renders retain the original audition date separately from
their later render timestamp.

Initial decisions are:

- Denis: former default, implemented 2026-08-27 and removed by SPEC-0004;
- Dmitri and Irina: audit-only rejected;
- kseniya, xenia, and baya: retained bot options from SPEC-0004;
- aidar and eugene: audit-only rejected;
- Aiden: selected default by SPEC-0005;
- Serena: retained as the second configurable Qwen voice by SPEC-0005;
- Vivian: audit-only rejected.

## Repository policy and verification

Only manifest-listed WAVs under `auditions/` generated from the checked-in synthetic
fixture are repository assets. Telegram/user-derived text and audio, arbitrary generated
audio, logs containing message content, and model weights remain excluded. The archive
is committed directly to ordinary Git, marked binary, and excluded from Python packages
and Docker contexts.

A network-free validator checks the prompt hash, schema, unique IDs and paths, chronology
fields, allowed decision states, file coverage, SHA-256, PCM16 mono headers, frames,
sample rate, and duration. Every WAV must be listed and every successful manifest entry
must have exactly one WAV. CI validates existing assets but never regenerates models.

New model revisions append directories and manifest entries. Existing prompt versions,
WAVs, hashes, render metadata, and decision events are never overwritten or deleted.
The current classification may advance only by appending a dated decision event and
updating the derived current field.

## Non-goals

- Model weights, Telegram/user content, Git LFS, perceptual scoring, ratings, a web UI,
  CI model inference, or multiple stochastic runs per combination.

## Acceptance criteria

- All eleven initial WAVs are present, playable, lossless, and manifest-valid.
- The Aiden entry is byte-identical to the accepted audition SHA-256
  `7c1dc7c820c01125d3898474a4b164146f86254d3cc98831b5486560c975793d`.
- README chronology and manifest dates distinguish original auditions, canonical render
  time, implementation, removal, selection, and rejection decisions.
- Tests reject prompt drift, stale metadata, unlisted WAVs, missing WAVs, hash changes,
  invalid headers, and invalid decision history.
- Build artifacts and container contexts contain no audition WAVs.

## Open questions

None.
