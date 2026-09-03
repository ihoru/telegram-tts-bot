---
id: "0017"
title: Rich text and media-caption input
status: accepted
created: 2026-09-03
updated: 2026-09-03
supersedes: null
---

# SPEC-0017: Rich text and media-caption input

## Summary

Process textual content from private Telegram messages whether Telegram supplies it as
ordinary message text, a media caption, or structured rich-message blocks.

## Context

The inherited v1 contract accepts only `Message.text`. A photo, video, document, or
other media message can carry user-visible text in `Message.caption`. Telegram can also
supply text as nested `Message.rich_message` blocks, including paragraphs inside lists.
The current filter routes both forms to unsupported-content guidance instead of TTS.

## Goals

- Voice private message text, media captions, and structured rich-message text through
  the same path.
- Apply the existing validation, queue, rendering, reply, and privacy behavior equally.
- Explain caption support in Russian and English help and BotFather copy.

## Non-goals

- Transcribing, describing, downloading, or interpreting attached media.
- Narrating formatting metadata, link targets, author names, forwarding metadata, or
  media metadata.
- Accepting groups, channels, stories, reactions, or other non-message updates.

## User-visible behavior

A private message is eligible for TTS when `Message.text`, `Message.caption`, or a
human-visible textual field in `Message.rich_message` is present. The bot flattens rich
paragraphs, lists, quotations, tables, captions, summaries, and other textual nodes in
document order while ignoring structural and media metadata. This includes forwarded
and copied content. Messages without extractable text keep receiving localized
unsupported-content guidance.

The existing empty-text and 4,096-character checks apply to the selected value.
Precedence is `Message.text`, then `Message.caption`, then `Message.rich_message`.

## Design and interfaces

The Telegram handler owns one extraction helper used by both its filter and render
path. Rich-message models are dumped to their structural mapping, then a recursive
allowlist extracts only human-visible text fields and traverses only content containers.
Downstream queue and speech interfaces continue receiving one `str`; they remain
unaware of Telegram message types and formatting.

## Configuration, security, and privacy

No configuration or trust boundary changes. Captions follow the same in-memory,
privacy-safe handling as ordinary text. The bot does not inspect or retain media.

## Failure cases

- Missing text and caption routes to existing unsupported-content guidance.
- Empty or overlong selected content uses the existing localized validation response.
- Queue, rendering, encoding, and Telegram delivery failures retain existing behavior.

## Acceptance criteria

- Formatted private text is voiced from `Message.text`.
- Private media captions are voiced from `Message.caption`.
- Nested private rich-message paragraphs are flattened and voiced in document order.
- Forwarded media captions follow the same path without narrating forwarding metadata.
- Unsupported media without a caption still receives localized guidance.
- Existing text-message behavior is unchanged.
- Russian and English help accurately describe caption support.

## Test plan

- Exercise text, caption, and a production-shaped nested rich message through the real
  aiogram dispatcher.
- Assert the content filter accepts captions and still rejects group messages.
- Retain unsupported-content coverage for messages without text or captions.
- Run the locked Ruff, formatting, mypy, and pytest checks.

## Delivery and rollback

Release the handler, tests, specification, and copy together. Rollback restores the
text-only filter and extraction behavior plus the prior copy; no data migration exists.

## Alternatives

Registering a separate caption handler would duplicate validation and rendering logic.
Parsing formatting entities would add complexity while producing the same plain text
that Telegram already provides.

## Open questions

None.
