---
id: "0010"
title: Bounded fair rendering queue and aggregated progress
status: accepted
created: 2026-08-28
updated: 2026-08-28
supersedes: "0003"
---

# SPEC-0010: Bounded fair rendering queue and aggregated progress

## Summary

Replace immediate overload rejection and one-shot activity with a bounded, fair,
memory-only rendering queue. Preserve existing active-render limits, show one aggregated
wait notice per user backlog, refresh one `record_voice` action per actively rendering
private chat, and caption successful voice notes with the configured model, voice,
render duration, and queue duration.

This specification supersedes SPEC-0003 and replaces the immediate-overload clauses
in the retained SPEC-0001 lineage. SPEC-0008's one-active-Qwen baseline, provider,
model, input, output, and local-only processing contracts remain in force.

## Context

Qwen rendering is intentionally limited to one active request. Rejecting every request
that arrives during a render makes ordinary forwarding bursts unreliable, while an
unbounded queue would create uncontrolled waiting and retention. Telegram chat actions
last five seconds or less, but sending one activity loop per queued request would create
redundant traffic and misleading status.

## Goals

- Queue a bounded burst without increasing active rendering concurrency.
- Preserve FIFO order per user and schedule users fairly without idling eligible slots.
- Bound queue retention by both item count and elapsed waiting time.
- Show aggregated queue feedback without message or chat-action storms.
- Keep accepted work memory-only, best-effort, and non-durable.
- Publish accurate bilingual privacy disclosures before releasing queue behavior.

## Non-goals

- Durable jobs, replay after restart, multiple polling replicas, queue positions, or ETA.
- Runtime voice selection, streaming audio, partial Telegram uploads, or active-render
  cancellation.
- Changing Qwen's one-render limit, Silero capacity validation, output audio format, or
  Telegram's own retention.
- Applying BotFather metadata remotely.

## User-visible behavior

Eligible private text is submitted to the process-local queue. Active capacity remains
governed by `TTS_MAX_CONCURRENCY` and `TTS_MAX_CONCURRENCY_PER_USER`. Waiting capacity
defaults to 20 requests globally and 10 for one user; active work is not counted as
waiting. When either waiting limit is reached, the newest request is rejected with a
localized global or per-user queue-full response. The per-user reason wins when both
limits apply.

Each user's requests start FIFO. Across users, the scheduler rotates round-robin and
fills every slot allowed by the active global and per-user limits. A waiting request
expires 600 seconds after acceptance. It is removed without rendering and receives a
localized retry response.

A continuously non-empty waiting queue for one user is one backlog episode. Five
seconds after the episode begins, the bot sends one localized wait notice only if that
user still has waiting work. Additional messages do not create timers or notices. The
episode resets when that user's waiting count reaches zero. Repeated identical
queue-full or expiry notices are coalesced per user over five seconds.

Queued users receive no chat action. When a request actually begins synthesis and
encoding, the bot sends `record_voice` to that private chat and refreshes it every four
seconds until the render finishes. A chat-scoped reference count prevents duplicate
activity loops if configured Silero concurrency allows more than one active request for
the same user. Telegram rate-limit delays are honored; other repeated failures back off
and remain non-fatal. Activity logs contain no chat ID, user identity, message text, or
Telegram error text.

Every successful voice note has a plain-text caption in one of these forms:

- `Qwen3-TTS (aiden) · render 5.123 s · queue 2.417 s`
- `Silero (xenia) · render 1.204 s · queue 0.000 s`

Labels remain English in both interface locales. Queue time runs from accepted
submission until actual rendering starts. Render time covers synthesis and the single
OGG/Opus encode. Telegram upload is excluded from both durations.

## Design and interfaces

`BotSpeechService.submit` returns either a typed rejection or an accepted render job.
The job exposes an awaitable start signal and one awaitable result. The successful
result contains `VoiceAudio`, queue duration, and render duration. Fairness, limits,
expiry, cancellation, timing, task consumption, and shutdown accounting stay inside
the speech-service module; Telegram types do not cross that seam.

The Telegram progress coordinator owns backlog notice coalescing and chat-scoped
activity. Model presentation stays outside the engine-neutral renderer: composition
injects an immutable model/voice descriptor selected from `TTS_VOICE`.

Caller cancellation removes work that has not started. Once rendering begins, caller
cancellation never frees active capacity early: the renderer finishes in the
background and its result or exception is consumed. A render failure releases capacity
and immediately schedules the next eligible job.

## Configuration, security, and privacy

- `TTS_MAX_QUEUE_SIZE`: positive integer, default 20.
- `TTS_MAX_QUEUE_SIZE_PER_USER`: positive integer, default 10 and no greater than the
  global waiting limit.
- `TTS_MAX_QUEUE_WAIT_SECONDS`: positive integer, default 600.
- Existing active-concurrency settings are unchanged.

Waiting text and the minimal numeric identifiers needed for fairness and replies stay
in process memory only. They are released on start/result completion, rejection,
expiry, cancellation, or shutdown. The queue creates no file, database, cache, or log
containing message content. Accepted work may be lost without notice on forced
termination, process failure, or Telegram outage.

The public Russian/English policy must disclose the bounded in-memory wait, its purpose,
the ten-minute pre-render maximum, and non-durability. Its updated public version is
built, published, and anonymously verified before bot queue behavior is released.

## Failure cases

- Queue-full and expiry responses are best-effort and never expose request content.
- Activity, wait-notice, caption upload, or shutdown-notice failures do not retry voice
  delivery or alter renderer accounting.
- Graceful shutdown stops handler admission, stops queue submissions, cancels queued
  jobs, wakes their handlers, sends one best-effort restart notice per affected user,
  finishes active renders and uploads, waits for handlers to become idle, closes the
  renderer, and finally closes the Telegram session.
- Forced termination may prevent queued cancellation notices. Active synchronous GPU
  work is not represented as safely cancellable.

## Acceptance criteria

- Defaults accept 20 waiting requests globally and 10 per user, excluding active work.
- Per-user FIFO, round-robin fairness, work conservation, rejection precedence, and
  600-second expiry are deterministic under concurrent submission and cancellation.
- A backlog produces at most one five-second wait notice and resets only after it empties.
- Queued work sends no activity; each active chat has one four-second activity stream.
- Captions contain the exact model, voice, render, and queue format to three decimals.
- Shutdown cannot deadlock queued handlers and keeps the Telegram session open for
  active uploads and best-effort notices.
- The published policy accurately describes queue processing in Russian and English.
- Locked Ruff lint, Ruff format, strict mypy, pytest, and privacy-site checks pass.

## Test plan

- Exercise queue boundaries, fair ordering, concurrent eligible slots, failures,
  cancellations, expiry, and shutdown using controlled renderers and a fake clock.
- Test backlog aggregation, duplicate-notice coalescing, chat activity reference counts,
  rate limits, backoff, failures, and cleanup without real sleeps.
- Test exact localized copy, model mapping, caption durations, upload failure, and real
  aiogram dispatcher routing.
- Regression-test shutdown stage ordering and idempotent cleanup.
- Build and test the policy site, deploy its exact committed source, and anonymously
  verify the public bilingual disclosure.

## Delivery and rollback

Publish and verify the policy first, then ship the bot code and three new settings.
Rollback restores the previous bot image; queued work is intentionally lost and no data
migration exists. The more accurate published policy may remain live after rollback.

## Alternatives

- Immediate overload rejection remains simpler but loses ordinary forwarding bursts.
- An unbounded or 100-item queue permits excessive waits and memory retention on the
  one-render Qwen baseline.
- Per-request chat-action loops create redundant Telegram traffic; queued chat actions
  also claim rendering activity before rendering starts.
- Durable persistence would provide replay but materially changes privacy, operations,
  and v1 scope.

## Open questions

None.
