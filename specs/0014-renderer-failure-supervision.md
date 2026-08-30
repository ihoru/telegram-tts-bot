---
id: "0014"
title: Renderer failure supervision
status: draft
priority: nice-to-have
created: 2026-08-30
updated: 2026-08-30
supersedes: null
---

# SPEC-0014: Renderer failure supervision

## Summary

Classify render failures by operational severity and prevent a broken model, CUDA
context, encoder, or executor from rapidly failing every waiting request. Open an
in-process circuit for fatal renderer failures, reject or abort outstanding work with
localized notices, emit content-free health evidence, and prefer a clean supervised
process restart over unproven in-process GPU recovery.

This is an unscheduled nice-to-have draft. It is not accepted for implementation and
does not change current admission or restart behavior.

## Context

The current speech module releases active capacity after any render exception and
immediately schedules the next eligible job. That is correct for an input-specific
failure but harmful when the loaded model or CUDA runtime has become unusable: the
entire bounded queue can be consumed by repeated failures before an operator or process
supervisor reacts.

Existing content-free exception types distinguish broad synthesis and encoding stages
but do not state whether the renderer remains usable. Runtime cleanup also needs a
deliberate signal path from a background render task to the polling composition module.

## Goals

- Distinguish request-specific, recoverable, and fatal renderer failures.
- Stop new admission and queue scheduling after a fatal renderer failure.
- Release waiting text promptly with one coalesced localized notice per user.
- Preserve correct active accounting and graceful cleanup under concurrent renders.
- Provide privacy-safe health logs and counters suitable for process supervision.
- Define a testable runtime signal for fatal failure.

## Non-goals

- Automatic model downloads, hot model replacement, or arbitrary CUDA recovery.
- Durable job replay, multiple replicas, or failover to a remote TTS provider.
- An Internet-facing health server, administration dashboard, or stored telemetry.
- Treating every user text or encoding error as proof that the renderer is broken.

## User-visible behavior

An ordinary request-specific render failure retains the localized retry response and
does not affect unrelated queued work. A fatal renderer failure changes the bot to a
temporarily unavailable state: waiting requests are aborted, new text is rejected, and
affected users receive one coalesced localized notice asking them to retry after the bot
restarts.

If deployment supervision is configured, the process exits through an orderly runtime
path and is restarted. No promise is made that queued work survives the restart. Any
other concurrently active render follows a failure policy that must be fixed before this
draft is accepted.

## Design and interfaces

Keep supervision inside the deep speech module because it already owns admission,
active accounting, scheduling, failure consumption, and shutdown. Do not expose circuit
state mutation to Telegram handlers.

Introduce a stable content-free classification, for example:

```python
class RenderFailureKind(StrEnum):
    REQUEST = "request"
    RECOVERABLE = "recoverable"
    FATAL = "fatal"
```

Provider and encoder implementations raise or translate typed failures at their natural
seams. The speech module converts fatal failure into typed job aborts and one runtime
failure signal. Its external interface remains centered on submission, job outcomes,
and lifecycle; circuit thresholds and bookkeeping are implementation details.

The composition module waits on polling completion and the fatal-renderer signal. When
fatal state wins, it stops handler admission, aborts waiting work, lets the established
cleanup order run, closes Telegram last, and exits nonzero so Docker or systemd can
restart it.

## Configuration, security, and privacy

Known fatal failures may open the circuit immediately. If unknown or recoverable errors
use a consecutive-failure threshold, that threshold and any observation window must be
immutable and validated at startup.

Logs and counters may include failure kind, provider, stage, consecutive count, queue
counts, active count, and lifecycle transition. They must not contain text, Telegram
identifiers, model prompts, exception messages from untrusted dependencies, generated
audio, or tokens.

Deployment documentation must state that fatal recovery depends on an external process
supervisor. The privacy policy should be reviewed; no persistent data or new third party
is intended.

## Failure cases

- Invalid or unsupported text fails one request and leaves the circuit closed.
- A known unusable model or CUDA state opens the circuit exactly once.
- Concurrent render completions after circuit opening release accounting exactly once.
- Waiting jobs are aborted without being scheduled after the circuit opens.
- Shutdown and fatal failure racing together share one idempotent cleanup path.
- Failure to notify Telegram never delays process cleanup indefinitely.
- A missing or misconfigured process supervisor produces downtime but no restart loop
  hidden as successful recovery.

## Acceptance criteria

- Typed tests cover request, recoverable, and fatal classifications at provider and
  encoder seams.
- A request-specific failure schedules the next eligible job under existing rules.
- A fatal failure prevents every later waiting job from entering the renderer.
- New submissions receive a typed temporarily-unavailable rejection while open.
- Waiting text is released and user notices remain coalesced and localized.
- Fatal state reaches the composition module and produces deterministic nonzero exit
  after the established cleanup order.
- Health logs and metrics are content-free and do not expose numeric identifiers.
- Locked Ruff, format, strict mypy, pytest, and relevant container checks pass.

## Test plan

- Script provider and encoder failures through fake renderer adapters.
- Exercise fatal failure with multiple waiting users and concurrent active Silero work.
- Race fatal signaling with shutdown, cancellation, expiry, and Telegram notification
  failure.
- Verify no queued text reaches the renderer after the circuit opens.
- Test the runtime with fake polling, renderer-failure, and cleanup signals.
- Run a container-level supervisor restart exercise without real user data.

## Delivery and rollback

If accepted, deliver typed errors, speech-module supervision, runtime signaling,
localized copy, deployment documentation, and tests together. Verify the real production
supervisor before deployment. Rollback restores failure-per-job behavior and must not
claim automatic renderer recovery.

## Alternatives

Always continuing maximizes availability for isolated failures but destroys a queue when
the renderer is permanently broken. In-process model reload is attractive but difficult
to prove safe after CUDA failures and complicates lifecycle ownership. An HTTP health
server adds deployment and security surface without fixing failure classification.

## Open questions

- Which current Qwen, Silero, PyTorch, and FFmpeg failures are definitively fatal?
- Should recoverable or unknown failures use a threshold, and over what time window?
- What happens to other active Silero renders when one render proves fatal?
- Should fatal state exit immediately after cleanup or remain unavailable for inspection?
- Which process supervisor and restart-loop safeguards are guaranteed in production?
