---
id: "0024"
title: Failure-isolated incoming update logging
status: accepted
created: 2026-09-13
updated: 2026-09-13
supersedes: "0018"
---

# SPEC-0024: Failure-isolated incoming update logging

## Summary

Incoming-update diagnostics must never prevent routing because a payload cannot be
serialized. Retain SPEC-0018's debug-only payloads and selected-handler logging.

## Context

An actual forwarded private message failed before routing: link-preview fields omitted
by Telegram became aiogram Default objects, which model_dump_json cannot serialize.
Serialization was also evaluated with DEBUG disabled, while aiogram errors were hidden.

## Goals

- Preserve delivery of supported messages with link-preview metadata.
- Serialize incoming payloads only when DEBUG is enabled.
- Continue dispatch after serialization failures.

## Non-goals

Change handler routing, replies, providers, queues, or general exception logging.

## User-visible behavior

Supported messages retain their existing TTS behavior, including forwarded text.
A diagnostic serialization failure does not discard the update.

## Design and interfaces

UpdateLoggingMiddleware checks isEnabledFor(DEBUG) before serializing. Serialize with
aliases, exclude_none=True, and exclude_unset=True to omit framework-injected defaults.
Catch serialization exceptions only around serialization; emit a warning containing
only the exception class and continue to the next middleware. Handler exceptions keep
propagating normally. Successful debug payloads and handler logs retain their names.

## Configuration, security, and privacy

No new settings. Debug payloads remain sensitive under SPEC-0018's access and retention
rules. Failure warnings contain no payload, exception message, identities, or traceback.

## Failure cases

An unserializable value produces one warning in DEBUG and does not prevent dispatch.
With DEBUG disabled, serialization is not attempted. Downstream failures are not caught.

## Acceptance criteria

- Real dispatcher tests deliver text with link-preview options at INFO and DEBUG.
- Unset defaults are omitted while explicitly supplied preview options are retained.
- Serialization failures still invoke the next handler exactly once.
- INFO does not serialize or emit payload logs.
- All required locked checks pass.

## Test plan

Use synthetic aiogram updates through Dispatcher.feed_update, plus middleware tests
for disabled logging, successful nested serialization, and serialization failure.
Recheck the original forward with the user through the temporary debug runner.

## Delivery and rollback

Deliver the middleware fix with its tests. No migration is required. Reverting restores
the known risk of dropping updates with link-preview metadata.

## Alternatives

Catching exceptions alone preserves routing but wastes work at INFO and loses valid
preview diagnostics. Disabling all debug logging removes useful troubleshooting data.

## Open questions

None.
