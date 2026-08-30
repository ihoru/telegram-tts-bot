---
id: "0012"
title: Reliable Telegram voice delivery
status: draft
priority: nice-to-have
created: 2026-08-30
updated: 2026-08-30
supersedes: null
---

# SPEC-0012: Reliable Telegram voice delivery

## Summary

Retry a narrowly defined set of transient Telegram voice-upload failures without
rendering the source text again. Keep the completed OGG payload only in memory while
delivery is outstanding, bound all retry time and attempts, and send a localized text
notice when delivery ultimately fails.

This is an unscheduled nice-to-have draft. It is not accepted for implementation and
does not change the current best-effort delivery contract.

## Context

The current handler renders a complete voice note and calls Telegram once. Any upload
exception is logged and swallowed, so an expensive successful render can disappear
without a response. Retrying every exception is also unsafe: a connection can fail after
Telegram accepted the upload, and Telegram does not provide an idempotency key for
`sendVoice`. A retry in that ambiguous state can create a duplicate voice note.

SPEC-0010 explicitly makes voice delivery non-retrying. If this draft is accepted, its
supersession relationship and all retained SPEC-0010 queue, progress, privacy, and
shutdown decisions must be recorded before implementation.

## Goals

- Preserve a successfully rendered payload across bounded delivery attempts.
- Honor explicit Telegram rate-limit delays.
- Retry only failures classified as safe enough by the accepted policy.
- Never synthesize or encode the source text again during delivery recovery.
- Tell the user when delivery definitively fails, when Telegram still accepts text.
- Keep delivery logs content-free and useful for operations.

## Non-goals

- Guaranteed exactly-once delivery, durable outbox storage, or replay after restart.
- Retrying arbitrary exceptions or hiding the possibility of duplicate delivery.
- Changing synthesis, encoding, queue fairness, render concurrency, or voice captions.
- Persisting generated audio, Telegram message content, or delivery requests.

## User-visible behavior

A successful first upload is unchanged. When Telegram returns an explicitly retryable
response, the bot waits according to the bounded retry policy and tries to upload the
same in-memory OGG payload again. Rendering progress does not restart and render time in
the caption remains the original render duration.

If every permitted attempt fails, the bot sends one localized reply explaining that the
voice note was created but could not be delivered and asking the user to try again. That
fallback is best-effort and is not recursively retried through the voice-delivery path.

No intermediate retry message is sent. A successful retry produces one ordinary voice
note unless Telegram accepted an earlier ambiguous request; that residual duplicate
risk must be documented in the accepted policy.

## Design and interfaces

Introduce a deep Telegram delivery module. Handlers construct one immutable delivery
request and receive one typed outcome; retry classification, delay handling, attempt
accounting, upload construction, and content-free logging remain inside the module.

An illustrative interface is:

```python
@dataclass(frozen=True, slots=True)
class VoiceDeliveryRequest:
    target: ReplyTarget
    rendered: RenderedVoice
    caption: str
    failure_text: str


async def deliver(request: VoiceDeliveryRequest) -> VoiceDeliveryOutcome: ...
```

`VoiceDeliveryOutcome` distinguishes delivered, definitively failed, and ambiguous
failure states without exposing Telegram exception text. The production adapter uses
the aiogram bot; tests provide a fake Telegram adapter with scripted responses.

The module accepts an injected sleep function and retry policy for deterministic tests.
It must reconstruct upload input safely for each attempt while retaining only the one
encoded byte payload already held by the request.

## Configuration, security, and privacy

The retry limit and total delivery window should be immutable process configuration if
operators need to tune them. Defaults must remain small and must be fixed before this
draft can be accepted.

The delivery module retains the generated OGG bytes and minimal numeric reply routing
data only until success, final failure, cancellation, or shutdown. It writes no audio or
message data to disk. Logs may contain attempt number, elapsed time, output byte count,
outcome category, and exception class, but never identifiers, source text, captions,
tokens, Telegram response bodies, or audio bytes.

The privacy policy must be reviewed before release. If bounded in-memory post-render
retention is materially longer than the current upload operation, publish updated
Russian and English wording before deployment.

## Failure cases

- `TelegramRetryAfter` delays by at least Telegram's requested duration, subject to the
  accepted total retry window.
- A definitively non-retryable Telegram error ends delivery immediately.
- An ambiguous transport failure follows the accepted duplicate-risk policy.
- Cancellation and shutdown stop further attempts without publishing partial state.
- Failure of the localized text fallback is logged once and otherwise remains non-fatal.
- A missing bot binding returns a typed failure without retrying.

## Acceptance criteria

- One render produces at most one in-memory OGG payload regardless of upload attempts.
- Scripted rate limiting retries the same payload after the required delay.
- Non-retryable failures make exactly one upload attempt.
- Retry attempts and elapsed retry time cannot exceed their configured bounds.
- Exhaustion attempts one localized text fallback and releases the audio bytes.
- Successful delivery, exhaustion, cancellation, and shutdown emit content-free logs.
- Existing queue accounting, caption timing, progress, and graceful shutdown behavior
  remain unchanged.
- Locked Ruff, format, strict mypy, and pytest checks pass.

## Test plan

- Use a scripted fake Telegram adapter for success, rate limiting, non-retryable errors,
  ambiguous transport errors, fallback failure, cancellation, and shutdown.
- Assert byte identity across attempts and prove the renderer is called exactly once.
- Use a fake clock and sleep function to verify attempt and elapsed-time bounds.
- Test exact Russian and English final-failure messages through the handler seam.
- Retain dispatcher-level coverage for reply targeting and voice captions.

## Delivery and rollback

If accepted, implement this independently before queue cancellation, active-render
progress, or per-user render profiles. Record whether it supersedes SPEC-0010 or only
replaces its voice-delivery failure clause. Rollback restores one-attempt best-effort
delivery; no stored data or migration exists.

## Alternatives

Durable delivery would enable replay but violates the current no-persistence product
contract. Retrying every network exception maximizes delivery probability but obscures
duplicate risk. Re-rendering after upload failure wastes GPU capacity and can produce
different audio, so it is excluded.

## Open questions

- Which aiogram and transport exceptions are safe enough to retry?
- What maximum attempt count and total delivery window should be used?
- Should ambiguous failures be retried despite the duplicate-delivery risk?
- Should retry settings be configurable or fixed implementation constants?
- Does the public privacy policy require new post-render retention wording?
