---
id: "0011"
title: Privacy-policy link in bot copy
status: accepted
created: 2026-08-30
updated: 2026-08-30
supersedes: null
---

# SPEC-0011: Privacy-policy link in bot copy

## Summary

Append the public privacy-policy link to the localized `/start` and `/help` responses so
users can reach the policy from the bot conversation itself. Retain all runtime,
localization, queue, synthesis, persistence, and BotFather contracts from SPEC-0008 and
SPEC-0010.

## Context

The bot explains its local processing and non-persistence behavior in `/start` and
`/help`, but those responses do not link to the full policy. The canonical launch pack
still names an older policy host.

## Goals

- Put the current public privacy-policy URL in both informational command responses.
- Localize the label while keeping the same policy URL in both interfaces.
- Keep the canonical BotFather launch pack synchronized with runtime copy.

## Non-goals

- Adding the link to queue notices, validation errors, failure responses, or voice-note
  captions.
- Changing the policy content, deployment, locale selection, or Telegram parse mode.

## User-visible behavior

Russian `/start` and `/help` responses end with a blank line followed by:

```text
Политика конфиденциальности: http://telegram-tts-bot.iho.su/
```

English `/start` and `/help` responses end with:

```text
Privacy policy: http://telegram-tts-bot.iho.su/
```

Telegram may auto-link the URL. The bot does not enable Markdown or HTML parsing for
these responses.

## Design and interfaces

The suffix remains part of the existing `START` and `HELP` values in
`telegram_tts_bot.localization`. No handler or message-key interface changes.

## Configuration, security, and privacy

No settings, secrets, retained data, or trust boundaries change. Anonymous HTTP access
to the supplied URL returns the public policy after redirecting to HTTPS.

## Failure cases

The URL is static copy. Existing best-effort command-response handling is unchanged.

## Acceptance criteria

- Russian and English `/start` and `/help` responses end with their localized policy
  label and the same URL.
- Other localized runtime responses do not gain the suffix.
- The BotFather launch pack identifies the new public policy host and shows matching
  command copy.
- Locked Ruff lint, Ruff format, strict mypy, and pytest pass.

## Test plan

- Assert the exact `/start` copy in both locales.
- Assert that `/help` ends with the policy line in both locales.
- Run the complete required local checks.

## Delivery and rollback

Ship as a copy-only bot update. Rollback restores the previous localization and launch
pack; no data migration is required.

## Alternatives

Appending the link to every text response would make routine queue and error notices
noisy without improving discovery after the user has seen `/start` or `/help`.

## Open questions

None.
