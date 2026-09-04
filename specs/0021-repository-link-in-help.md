---
id: "0021"
title: Repository link in help
status: implemented
created: 2026-09-04
updated: 2026-09-04
supersedes: null
---

# SPEC-0021: Repository link in help

## Summary

Add the user-requested GitHub repository link to both localized `/help` responses.
This extends the informational copy from SPEC-0011 and SPEC-0019.

## Context

The help response links to the privacy policy but does not identify the source repository.

## Goals

- Make the repository discoverable from `/help` in both supported locales.

## Non-goals

Changing `/start`, other responses, command routing, or Telegram parse mode.

## User-visible behavior

Immediately before the existing privacy-policy paragraph, add a separate paragraph:

- English: `Repository: https://github.com/ihoru/telegram-tts-bot`
- Russian: `Репозиторий: https://github.com/ihoru/telegram-tts-bot`

Use the existing plain-text response format with a bare URL.

## Design and interfaces

Keep the URL and localized help copy in `telegram_tts_bot.localization`. Synchronize
the `/help` examples in `specs/BOTFATHER.md`.

## Configuration, security, and privacy

No configuration, secrets, retained data, or trust boundaries change.

## Failure cases

The link is static copy; existing command-response failure handling remains unchanged.

## Acceptance criteria

- Both `/help` responses contain the exact repository URL and localized label.
- The existing privacy-policy paragraph remains last.
- `/start` and other responses remain unchanged.
- The documented help examples match the runtime copy.

## Test plan

Update the existing localized help-copy assertions and run the required locked Ruff,
mypy, and pytest checks.

## Delivery and rollback

Implemented by the commit introducing this specification, titled
`feat: add repository link to help command`.

Ship with the next bot deployment. Revert the copy changes to roll back; no migration
or BotFather action is needed.

## Alternatives

Adding the URL to `/start` would extend the change beyond the requested command.

## Open questions

None.
