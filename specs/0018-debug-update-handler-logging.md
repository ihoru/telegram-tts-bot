---
id: "0018"
title: Debug incoming update and handler logging
status: accepted
created: 2026-09-03
updated: 2026-09-03
supersedes: null
---

# SPEC-0018: Debug incoming update and handler logging

## Summary

When debug logging is enabled, emit one compact JSON log for every Telegram update and
identify the concrete handler that processes each matched update.

## Context

The suppressed aiogram event logger makes routing diagnostics difficult. Existing
application logs intentionally exclude message content and Telegram identity data, so
logging complete incoming updates is restricted to explicit debug operation.

## Goals

- Log every incoming Telegram update at `DEBUG` as one-line JSON.
- Remove null-valued fields recursively to keep each payload compact.
- Log the selected handler name after its invocation, correlated by update ID.

## Non-goals

- Emit incoming payloads at the default `INFO` log level.
- Persist logs in an application database or file.
- Configure hosting-provider retention, rotation, or access control.
- Change routing, filters, replies, synthesis, or queue behavior.

## User-visible behavior

Bot replies and routing remain unchanged. Operators who explicitly enable `DEBUG` can
inspect incoming update payloads and the handler selected for matched message updates.

## Design and interfaces

An update-level outer middleware serializes the aiogram `Update` with aliases and
`exclude_none=True`. A message-level inner middleware reads aiogram's selected handler
object after filters pass and logs its callback name. The handler log includes the
Telegram update ID. Unmatched update types have an incoming JSON log but no handler log.

## Configuration, security, and privacy

Debug JSON can contain message text, names, usernames, numeric identifiers, forwarding
details, file identifiers, and other Telegram metadata. It must never contain the bot
token. The application writes these records only through standard logging when the
configured level enables `DEBUG`; deployment infrastructure controls storage, access,
rotation, and deletion. Operators must restrict debug-log access and retention
accordingly. Null fields are omitted, but no other payload fields are redacted.

## Failure cases

- A handler exception still emits its handler identification before propagating normally.
- An update without a matching message handler emits only its incoming JSON record.
- Logging does not alter handler return values or suppress exceptions.

## Acceptance criteria

- Serialized debug updates contain no JSON null values.
- Every received update emits one `incoming_update` record when `DEBUG` is enabled.
- Every selected message handler emits one `update_processed` debug record with update ID
  and callback name.
- Default `INFO` operation does not emit payload or selected-handler records.
- The public privacy-policy source discloses debug payload logging and hosting retention.
- Locked Ruff, format, mypy, and pytest checks pass.

## Test plan

- Unit-test compact debug serialization with an update containing optional null fields.
- Unit-test selected callback naming and update-ID correlation.
- Run the repository's locked Ruff, format, mypy, and pytest checks.

## Delivery and rollback

Deploy the policy update with the bot change. Rollback removes both logging middlewares
and restores the previous policy wording.

## Alternatives

Keeping aiogram's generic event logger suppressed avoids sensitive payloads but does not
provide the requested routing diagnostics. `INFO` logging was rejected because it would
emit sensitive payloads during normal production operation.

## Open questions

None.
