---
id: "0016"
title: Per-user voice and speed profiles
status: draft
priority: nice-to-have
created: 2026-08-30
updated: 2026-08-30
supersedes: null
---

# SPEC-0016: Per-user voice and speed profiles

## Summary

Let private-chat users select a voice and playback speed from a bounded operator-approved
set, retain the preference only in process memory, and snapshot it into each request at
queue admission. Keep one startup-selected TTS backend per process, avoid loading both
Qwen and Silero for selection, and show the actual voice and speed in each result caption.

This is an unscheduled nice-to-have draft. It is not accepted for implementation and
does not change the current startup-selected voice contract.

## Context

The bot currently selects one voice at process startup and constructs a voice-specific
renderer. Qwen Aiden and Serena share one model family, and the selected Silero speakers
share another, but switching between those backends has different GPU, CPU, memory, and
licensing consequences.

Per-user settings also introduce short-lived user state. A user can change settings
while older messages wait in the queue, so the selected render profile must be captured
at acceptance instead of read when rendering eventually starts.

## Goals

- Offer discoverable localized voice and speed controls in private chats.
- Restrict choices to one already loaded backend and an operator-approved set.
- Keep preferences memory-only and reset them predictably on process restart.
- Snapshot one immutable render profile into every accepted request.
- Preserve queue fairness, no-persistence behavior, and one-render Qwen capacity.
- Validate output quality through the existing chronological audition process.

## Non-goals

- Loading Qwen and Silero simultaneously only to offer every voice.
- Persisting preferences, synchronizing them across replicas, or adding user accounts.
- Arbitrary model paths, uploaded voices, voice cloning, or free-form speed values.
- Language translation, SSML, pronunciation dictionaries, or per-message prompt text.
- Changing a request's profile after it has entered the queue.

## User-visible behavior

`/voice` presents only the configured backend's allowed voices using inline controls and
text-command fallbacks. `/speed` presents a small accepted set of multipliers. `/settings`
shows the current effective voice and speed and explains that settings reset when the bot
restarts.

Changing a preference affects only requests submitted afterward. Waiting and active
requests retain the voice and speed captured when they were accepted. The process-wide
default applies to users without an in-memory override.

Each successful voice caption identifies the actual model, voice, render duration, queue
duration, and non-default speed according to an exact format fixed before acceptance.
Unsupported or stale callback choices receive localized guidance and do not enter the
render queue.

## Design and interfaces

Add an in-memory user-preferences module with a small interface for reading, setting, and
resetting one validated profile. Telegram handlers own command and callback parsing; the
preferences module owns validation and state replacement.

Represent accepted work with an immutable engine-neutral request:

```python
@dataclass(frozen=True, slots=True)
class RenderProfile:
    voice: str
    speed: float


@dataclass(frozen=True, slots=True)
class RenderRequest:
    text: str
    profile: RenderProfile
```

`BotSpeechService.submit` receives the complete request and preserves it unchanged until
start. `VoiceRenderer` selects the speaker within its already loaded provider adapter and
applies the accepted speed transformation in the encoding path. Provider-specific voice
identifiers do not leak into queue scheduling logic.

SPEC-0015's progress reporter, if accepted first, remains orthogonal to the render
profile. Progress events must not expose the user ID or source text.

## Configuration, security, and privacy

Startup configuration selects one backend, its default voice, and the subset of voices
offered to users. Configuration must reject voices from another backend and retain
Qwen's one-active-render requirement.

The preferences module retains only numeric Telegram user ID, voice identifier, and
speed multiplier until restart or an explicit reset. It stores no text or audio and
writes no files. Logs record only setting kind and outcome, never user identity or the
full callback payload.

The Russian and English privacy policy must disclose process-memory preference retention
before release. Runtime help and BotFather command metadata must describe `/voice`,
`/speed`, and `/settings`. Silero licensing remains subject to the existing
NonCommercial restriction.

## Failure cases

- Unsupported voice or speed input is rejected before queue admission.
- A callback referring to a no-longer-allowed option leaves preferences unchanged.
- Restart loses overrides and restores configured defaults as documented.
- A preference change racing with submission is resolved by one atomic profile snapshot.
- Provider or encoder failure follows SPEC-0014's eventual failure classification.
- Speed processing failure fails the complete render and publishes no partial voice note.

## Acceptance criteria

- Only voices from the loaded backend can be selected or submitted for rendering.
- Every accepted request uses exactly the profile visible at its admission point.
- Later preference changes do not affect waiting or active jobs.
- Preferences survive multiple requests in one process and disappear after restart.
- Every allowed speed produces valid mono 48 kHz OGG/Opus output.
- Auditions establish acceptable quality for every allowed backend, voice, and speed.
- Captions, help, callbacks, and BotFather commands are exact in Russian and English.
- No new database, cache, file, remote provider, or cross-replica state is introduced.
- Locked Ruff, format, strict mypy, pytest, audition, and relevant real-model checks pass.

## Test plan

- Test preference validation, defaults, changes, resets, and restart with in-memory state.
- Race profile changes against queue admission and assert immutable request snapshots.
- Exercise Qwen and Silero allowed sets independently; reject cross-backend voices.
- Verify fixed speed transformations with synthetic audio and FFprobe assertions.
- Run approved real-model auditions at every proposed speed before acceptance.
- Feed commands and callback queries through real aiogram dispatcher routing.
- Regression-test queue fairness, captions, CLI rendering, shutdown, and privacy-safe logs.

## Delivery and rollback

If accepted, first record and approve the voice/speed audition evidence, then implement
the request and provider interfaces, preferences, Telegram controls, localization,
BotFather pack, privacy update, and tests. Publish and anonymously verify privacy wording
before deploying the bot behavior. Rollback removes user controls and restores the
startup default; in-memory overrides require no migration.

## Alternatives

Loading both backends maximizes choice but expands startup time, memory, licensing, and
failure surface. Persisting preferences improves continuity but conflicts with the
current no-persistence product. Free-form speed values are flexible but difficult to
validate for intelligibility and encoder support. Reading preferences at render start
would make queued requests change unexpectedly.

## Open questions

- Should the Qwen and Silero deployments expose all voices in their own backend?
- Which fixed speed multipliers pass listening review?
- Should captions always show speed or only show a non-default value?
- Should users be able to reset individual settings or only the complete profile?
- Is process-lifetime retention sufficient, or should this feature remain deferred until
  persistence becomes an accepted product direction?
