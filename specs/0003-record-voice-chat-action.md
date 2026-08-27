---
id: "0003"
title: Record-voice chat action
status: accepted
created: 2026-08-27
updated: 2026-08-27
supersedes: null
---

# SPEC-0003: Record-voice chat action

## Summary

Show Telegram's native "recording voice" activity before each eligible text-to-speech
render attempt so users receive immediate feedback while synthesis and encoding run.
This additive contract leaves SPEC-0002 and the underlying SPEC-0001 runtime behavior
unchanged.

## Context

Local speech rendering can take a noticeable amount of time. The bot currently remains
visually silent until it uploads the completed voice note. Telegram's `sendChatAction`
method provides a transient status intended for this kind of work.

## Goals

- Send exactly one `record_voice` chat action after text validation and before rendering.
- Apply the same behavior to direct, copied, and forwarded private text.
- Keep speech delivery working if Telegram rejects the non-essential activity call.

## Non-goals

- Refresh the action periodically after Telegram's status expires.
- Send activity for commands, invalid text, unsupported content, groups, or channels.
- Change rendering, admission limits, output format, persistence, or localization.

## User-visible behavior

For eligible private text, the bot sends `SendChatAction(action=record_voice)` to the
same chat immediately before calling the existing non-queuing render service. Telegram
may display the status for up to five seconds and clears it when the voice note arrives.

The activity call happens before admission is known, so it can briefly appear when the
render service immediately rejects an overloaded request. This does not create a queue
or consume a render slot.

## Design and interfaces

The Telegram handler owns the activity call. It uses the bot bound to the incoming
`Message`, the message's chat ID, and `aiogram.enums.ChatAction.RECORD_VOICE`. The call
is awaited before render timing starts and before `BotSpeechService.try_render` runs.
Speech services and renderers remain independent of Telegram APIs.

## Configuration, security, and privacy

No configuration or persistence is added. Failure logs contain only the action kind and
exception class; they contain no chat ID, user identity, message text, or Telegram error
text.

## Failure cases

If `sendChatAction` raises, the handler logs a privacy-safe warning and continues with
the render attempt. Existing render, overload, upload, and shutdown behavior is
unchanged.

## Acceptance criteria

- Valid direct and forwarded private text await one `record_voice` action before render.
- Commands, invalid text, unsupported content, and non-private messages send no action.
- Activity failure does not prevent rendering or voice delivery.
- Activity failure logs expose neither input nor Telegram identity data.
- Existing lint, format, type, and test checks pass.

## Test plan

- Assert the exact chat ID and `ChatAction.RECORD_VOICE` value.
- Assert call ordering: activity, render, then voice upload.
- Assert invalid text does not send activity.
- Assert activity failure still renders and logs only safe diagnostics.
- Run the repository's locked Ruff, mypy, and pytest checks.

## Delivery and rollback

Ship as a backward-compatible handler change. Rollback removes the activity helper and
its invocation; no data or configuration migration exists.

## Alternatives

- `ChatActionSender.record_voice` would refresh the status periodically, but one explicit
  `SendChatAction` call is the requested behavior and avoids another lifecycle task.
- Treating activity failure as fatal would make a cosmetic indicator less reliable than
  the core voice response.

## Open questions

None.
