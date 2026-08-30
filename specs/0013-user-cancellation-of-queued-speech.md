---
id: "0013"
title: User cancellation of queued speech
status: draft
priority: nice-to-have
created: 2026-08-30
updated: 2026-08-30
supersedes: null
---

# SPEC-0013: User cancellation of queued speech

## Summary

Add a localized `/cancel` command that atomically removes all waiting requests owned by
the requesting user while allowing any already active render to finish. Send one summary
reply, release cancelled text immediately, and avoid one cancellation message per
awakened request handler.

This is an unscheduled nice-to-have draft. It is not accepted for implementation and
does not add a public command yet.

## Context

The bounded queue already removes an individual waiting job when its caller disappears,
but users have no Telegram control for correcting an accidental forwarding burst or
withdrawing text that has not started. Active synchronous GPU work cannot be represented
as safely cancellable and must retain the existing finish-in-background behavior.

Cancellation races with fair scheduling: a waiting request can become active while the
command is handled. The speech module must define one atomic linearization point so the
reported counts and released text match the actual queue state.

## Goals

- Give each user one predictable command for withdrawing their waiting work.
- Preserve active-render completion and existing global and per-user capacity rules.
- Release cancelled source text and expiry tasks promptly.
- Return one accurate localized summary instead of per-job message noise.
- Keep queue locking, race handling, and job completion inside the speech module.

## Non-goals

- Interrupting active synthesis, terminating worker threads, or cancelling Telegram
  uploads already in progress.
- Cancelling another user's work, an arbitrary global queue, or one request by hidden ID.
- Durable cancellation history, undo, or replay after restart.
- Adding `/status`, queue positions, or ETA as part of this change.

## User-visible behavior

`/cancel` works only in a private chat and applies to the Telegram user issuing it. The
recommended initial behavior is to cancel every request that is still waiting at the
command's atomic queue snapshot.

The bot sends exactly one localized response in one of these semantic forms:

- no waiting requests existed;
- `N` waiting requests were cancelled;
- `N` waiting requests were cancelled and one or more active renders will still finish.

Queued request handlers awakened by this operation send no additional cancellation
messages. Voice notes for work that crossed into active state before cancellation may
still arrive normally.

The command must be registered before the broad text handler so `/cancel` is never sent
to speech synthesis.

## Design and interfaces

Deepen the existing speech module with one user-level cancellation operation rather than
exposing queues or `RenderJob` instances to Telegram handlers:

```python
@dataclass(frozen=True, slots=True)
class CancellationSummary:
    cancelled_waiting: int
    active: int


async def cancel_waiting(user_id: int) -> CancellationSummary: ...
```

The operation acquires the same lock used by admission and scheduling. It removes every
currently waiting job for that user, cancels each expiry timer, releases text, completes
the jobs with a distinct `USER_CANCELLED` abort reason, updates rotation and backlog
state, and schedules newly eligible work before returning.

Handlers that receive `USER_CANCELLED` finish silently because the command handler owns
the single summary reply. Other abort reasons retain their existing localized behavior.
The Telegram handler knows only the summary, not queue internals.

## Configuration, security, and privacy

No configuration or persistence is added. Authorization uses the numeric Telegram user
ID already used for per-user fairness. The command cannot accept another user ID.

Cancelled text and reply routing data are released before the method returns. Logs may
contain aggregate counts and outcome kinds but never user IDs, chat IDs, message IDs,
source text, usernames, or Telegram exception text.

The BotFather command list, runtime help, and public documentation must be updated in
Russian and English before release. The privacy policy should be reviewed, although the
feature reduces retained data and is not expected to require expanded collection.

## Failure cases

- A request scheduled before the cancellation lock is acquired remains active.
- A request still waiting when the lock is acquired is cancelled exactly once.
- Repeated or concurrent `/cancel` commands return consistent non-negative summaries.
- Telegram failure while sending the summary does not restore cancelled work.
- Shutdown racing with `/cancel` does not deadlock or double-complete jobs.
- Progress backlog timers are released when the cancelled backlog becomes empty.

## Acceptance criteria

- `/cancel` is routed as a command and never synthesized.
- All and only the caller's waiting jobs at the atomic snapshot are cancelled.
- Active renders are never interrupted and their capacity remains held until completion.
- Every cancelled job releases its text and expiry task promptly.
- One command creates at most one user-visible cancellation summary.
- Per-user FIFO order, round-robin fairness, queue counts, and work conservation remain
  correct after cancellation.
- Exact Russian and English copy and BotFather metadata are synchronized.
- Locked Ruff, format, strict mypy, and pytest checks pass.

## Test plan

- Exercise empty, one-item, and multi-item cancellation through the speech interface.
- Race cancellation against scheduling with a controlled renderer and fake clock.
- Test cancellation during another user's active render and under Silero concurrency.
- Verify expiry tasks, rotation state, and backlog progress are cleaned up.
- Feed real aiogram command updates through the dispatcher and assert one reply.
- Regression-test shutdown races and existing caller-cancellation behavior.

## Delivery and rollback

If accepted, update the numbered specification, runtime localization, BotFather launch
pack, and bot code together. Apply BotFather command metadata during the release and
verify both locales. Rollback removes the command; queued work remains memory-only and
requires no migration.

## Alternatives

Reply-targeted single-job cancellation offers finer control but is harder to discover,
depends on Telegram reply context, and exposes more queue identity. Active cancellation
would require unsafe assumptions about synchronous GPU work. Cancelling the latest job
only is surprising after a forwarding burst.

## Open questions

- Should `/cancel` cancel every waiting request or support reply-targeted cancellation?
- What exact Russian and English pluralized summaries should be used?
- Should the summary report the number of active renders or only say that active work
  cannot be cancelled?
- Must any existing queue-wait message be edited after cancellation?
