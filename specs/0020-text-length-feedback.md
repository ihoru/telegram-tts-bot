---
id: "0020"
title: Text length feedback
status: accepted
created: 2026-09-03
updated: 2026-09-03
supersedes: null
---

# SPEC-0020: Text length feedback

## Summary

Show the actual text length and the configured maximum when rejecting overlong input.
This extends the validation feedback inherited by SPEC-0017.

## Context

The handler already defines `MAX_TELEGRAM_TEXT_LENGTH`, but localized error messages
duplicate the numeric maximum and omit the actual length.

## Goals

- Display the actual and maximum character counts in both supported locales.
- Keep the validation limit and displayed maximum controlled by one constant.
- Increase the maximum accepted length to 10,096 characters.

## Non-goals

Changing text extraction, counting, or queue behavior.

## User-visible behavior

English: `The text is too long: {length} characters. The maximum is {max_length} characters.`
Russian: `Текст слишком длинный: {length} символов. Максимум — {max_length} символов.`
Counts are ungrouped decimal integers, measured with Python `len` on extracted text.

## Design and interfaces

Use `MAX_TELEGRAM_TEXT_LENGTH = 10096` in the handler as the single runtime limit.
Format the localized template with the actual count and this constant before replying.

## Configuration, security, and privacy

No new settings or retained data. Replies contain counts, not the rejected text.

## Failure cases

Overlong input is rejected before submission; existing admission cleanup is preserved.

## Acceptance criteria

- Both localized errors show the actual count and the handler's maximum.
- Changing the constant updates validation and the displayed maximum together.
- Existing empty-input feedback remains unchanged.

## Test plan

Update invalid-input assertions for both locales and run the required locked checks.

## Delivery and rollback

Ship templates and handler formatting together; revert both together to roll back.

## Alternatives

Duplicating the maximum in translations lets the copy drift when the limit changes.

## Open questions

None.
