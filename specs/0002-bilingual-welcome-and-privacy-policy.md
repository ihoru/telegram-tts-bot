---
id: "0002"
title: Bilingual welcome and privacy policy
status: accepted
created: 2026-08-27
updated: 2026-08-27
supersedes: "0001"
---

# SPEC-0002: Bilingual welcome and privacy policy

## Summary

Keep every runtime and delivery decision from SPEC-0001 while making the localized
`/start` copy an explicit welcome message and publishing a public Russian-and-English
privacy policy whose URL can be configured in BotFather.

## Context

The launch pack contains localized `/start` copy but does not identify it as the welcome
message. It also makes privacy claims without providing the public policy URL required
for a complete BotFather profile. The policy must distinguish the bot application's
in-memory processing from Telegram's independent handling of messages and voice notes.

All SPEC-0001 decisions not explicitly changed below remain in force.

## Goals

- Provide concise, friendly Russian and English welcome messages with equivalent meaning.
- State that the bot accepts regular or forwarded text and produces Russian voice notes.
- Publish a stable, publicly reachable bilingual privacy-policy page.
- Record the deployed policy URL in the canonical BotFather launch pack.

## Non-goals

- Change synthesis, supported chat types, commands, admission limits, or retention.
- Add application-set cookies, analytics, forms, authentication, persistence, or a
  support database.
- Claim control over Telegram's own data handling or retention.

## User-visible behavior

`/start` returns the localized welcome message selected by the existing `ru*` rule. The
message introduces Vslukh, explains that regular and forwarded text becomes a Russian
voice note, states that synthesis is local and the bot stores neither messages nor
generated audio, and points to `/help`.

The policy page offers Russian and English on one route, defaults to readable bilingual
content without requiring JavaScript, and includes an effective date. It explains what
the bot processes, why, the absence of application-level message/audio persistence,
limited content-free operational logging, Telegram as an independent service, public
bot access, security limits, and how policy changes are communicated.

## Design and interfaces

The exact welcome copy and policy URL live in `specs/BOTFATHER.md`; runtime welcome copy
remains in `telegram_tts_bot.localization`. The policy site is maintained in a dedicated
repository subdirectory and published through Sites. It has one responsive, accessible
route and no application database, account, form, data API, or external assets.

## Configuration, security, and privacy

The bot processes message text, generated WAV/OGG bytes, language code, numeric user ID,
chat type, and message/reply identifiers for localization, admission control, synthesis,
and Telegram delivery. It does not use forwarding metadata for narration and does not
write messages or generated audio to application storage. Operational logs may include
event type, character count, duration, output byte count, and exception class, but not
tokens, message text, names, usernames, or forwarding data.

Telegram necessarily transports the incoming message and outgoing voice note under
Telegram's own terms and privacy policy. The policy-site code sets no cookies, loads no
analytics, and collects no form input; its host may still process ordinary request and
security metadata and set protective cookies.

## Failure cases

- If publication fails, do not add a non-working or private URL to the launch pack.
- If the live URL cannot be reached publicly, it is not suitable for BotFather.
- If runtime and launch-pack welcome text diverge, validation fails.
- If a policy claim exceeds the accepted implementation facts, narrow the claim before
  publishing rather than changing runtime behavior.

## Acceptance criteria

- `specs/BOTFATHER.md` labels and contains equivalent Russian and English welcome copy.
- The runtime localization uses exactly that copy and focused tests cover both locales.
- A single public URL serves the bilingual policy without sign-in.
- The policy states the application's actual processing, storage, logging, and third-party
  boundary without promising how Telegram retains data.
- The launch pack records the exact deployed URL and adds it to the setup checklist.
- Existing lint, format, type, and test checks pass.

## Test plan

- Assert the full Russian and English `/start` responses through localization tests.
- Build the policy site successfully.
- Confirm the production deployment reaches a terminal successful state and returns a
  public URL.
- Run the repository's locked Ruff, mypy, and pytest checks.

## Delivery and rollback

Publish the policy site before inserting its URL in the launch pack. Rollback restores
the previous welcome copy and removes the BotFather URL; the last successful Sites
version remains available for redeployment. No user data migration exists.

## Alternatives

- A private Sites deployment cannot serve as BotFather's public policy URL.
- A policy hosted only as repository Markdown is less suitable for users opening it from
  Telegram and does not satisfy the requested Sites publication.
- Separate language routes add navigation and maintenance without improving this short
  policy; one bilingual page keeps both versions visibly aligned.

## Open questions

None.
