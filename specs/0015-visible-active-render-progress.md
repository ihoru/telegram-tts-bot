---
id: "0015"
title: Visible active-render progress
status: draft
priority: nice-to-have
created: 2026-08-30
updated: 2026-08-30
supersedes: null
---

# SPEC-0015: Visible active-render progress

## Summary

Expose content-free synthesis milestones through an engine-neutral render-progress seam
and show one throttled, editable Telegram progress message for long active renders. Keep
the existing `record_voice` activity, send no progress for queued work, avoid message
storms, and make every progress failure non-fatal to rendering and delivery.

This is an unscheduled nice-to-have draft. It is not accepted for implementation and
does not change current Telegram progress behavior.

## Context

The CLI can report Qwen model and chunk progress through provider logging, while Telegram
users see only the `record_voice` action after active rendering begins. A long multi-
chunk render can therefore appear stuck even though chunks are completing normally.

Telegram concerns must not enter synthesizer implementations. At the same time, progress
needs a real seam rather than parsing logs: the CLI and Telegram are two adapters for the
same engine-neutral milestone stream.

## Goals

- Report content-free render stages and completed/total work where known.
- Show visible progress only after a render has remained active long enough to benefit.
- Use one Telegram message per active request and edit it at a bounded rate.
- Preserve chat-scoped `record_voice` behavior throughout the active render.
- Keep progress failures independent from synthesis, encoding, and voice delivery.
- Reuse the same progress interface for CLI and Telegram adapters.

## Non-goals

- Streaming partial audio, uploading partial voice notes, or parallel chunk synthesis.
- Queue positions, wait-time ETA, token-level progress, or source-text previews.
- Guaranteeing a percentage when a provider does not know total work.
- Changing chunk boundaries, model generation parameters, concurrency, or output format.

## User-visible behavior

Queued requests retain the existing aggregated queue notice and receive no render
progress or chat action. When a request becomes active, `record_voice` starts normally.
If rendering finishes before the configured visibility delay, no progress message is
sent.

For a longer render, the bot replies once with localized status and edits that same
message at meaningful milestones, for example `Rendering speech: chunk 2 of 7`. Edits
are throttled and repeated identical states are coalesced. The message contains no source
text, model prompt, generated tokens, identifiers, or exception details.

On success, the message follows an accepted completion policy while the ordinary voice
note remains the authoritative result. On failure, it may be edited to a localized
failure state, but existing failure replies must not be duplicated.

## Design and interfaces

Introduce an immutable engine-neutral event such as:

```python
@dataclass(frozen=True, slots=True)
class RenderProgress:
    stage: RenderStage
    completed: int | None = None
    total: int | None = None
```

The renderer accepts one optional progress reporter as part of a render request or
render invocation. Because synthesis runs in a worker thread, reporting must be
thread-safe, non-blocking, ordered per request, and unable to raise into model code.

The CLI adapter formats events on stderr. The Telegram adapter forwards them onto the
event loop and delegates message creation, editing, throttling, rate-limit handling, and
cleanup to `TelegramProgressCoordinator`. Provider adapters translate their internal
work into the common event vocabulary without importing Telegram.

SPEC-0014's eventual failure classification should be resolved before this spec is
accepted so terminal progress states do not invent a competing error model.

## Configuration, security, and privacy

The visibility delay and edit throttle may be fixed constants or immutable validated
settings. Defaults must avoid Telegram rate-limit pressure and must be decided before
acceptance.

Progress state retains only stage names, counts, one Telegram message reference, and the
existing request routing data for the active render. It must be released on delivery,
failure, cancellation, or shutdown. No progress state is written to disk or logged with
user identifiers.

Review runtime help, BotFather copy, and the public privacy policy before release. No new
third party or persistent data is intended.

## Failure cases

- A Telegram progress send or edit failure is logged content-free and never fails render.
- `TelegramRetryAfter` delays later edits without blocking synthesis.
- Out-of-order or late thread events cannot recreate progress after terminal cleanup.
- Unknown totals produce stage-only text rather than a fabricated percentage.
- Shutdown stops progress tasks before the Telegram session closes.
- Fast renders do not leave pending visibility timers or create Telegram messages.

## Acceptance criteria

- Qwen multi-chunk renders emit ordered start, chunk, assembly, and completion events.
- Silero emits the best truthful milestones available without fabricated chunk totals.
- Fast renders create no progress message after the visibility delay is cancelled.
- Long renders create at most one progress message and respect the edit throttle.
- Queued work creates neither render progress nor `record_voice` activity.
- Progress failures do not change render, queue, caption, or delivery outcomes.
- CLI progress retains stderr-only output and Telegram uses localized message text.
- All progress state is content-free and released on every terminal path.
- Locked Ruff, format, strict mypy, and pytest checks pass.

## Test plan

- Test provider event sequences with fake multi-chunk and unknown-total synthesizers.
- Test thread-to-event-loop delivery, ordering, late events, and reporter exceptions.
- Use fake time for visibility delay, throttling, coalescing, and rate limiting.
- Exercise success, render failure, delivery failure, cancellation, and shutdown cleanup.
- Feed real aiogram updates through the dispatcher and assert reply/edit targeting.
- Regression-test current backlog notices and chat-scoped activity reference counts.

## Delivery and rollback

If accepted, implement the engine-neutral events and CLI adapter before Telegram message
editing, then add the Telegram adapter and localized copy. Preserve existing progress
behavior until the complete contract passes tests. Rollback removes progress messages
and events while retaining `record_voice` and queue notices.

## Alternatives

Parsing provider logs couples behavior to presentation and is not a stable interface.
Sending a new message for every chunk creates chat noise and rate-limit risk. Showing a
percentage from generated token counts would be misleading because final work is not
known reliably. Streaming audio is a separate product and architecture decision.

## Open questions

- What visibility delay and minimum edit interval should be used?
- Should completion edit the progress message, delete it, or leave the last milestone?
- Should an existing queue-wait message be reused when a queued request becomes active?
- Which milestones can Silero report truthfully with the current implementation?
- Should progress settings be configurable or fixed implementation constants?
