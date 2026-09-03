---
id: "0019"
title: Read Aloud rebrand
status: accepted
created: 2026-09-03
updated: 2026-09-03
supersedes: null
---

# SPEC-0019: Read Aloud rebrand

## Summary

Rename the bot to **Read Aloud** everywhere the product identity appears. Replace the
retired public name in Telegram copy, BotFather metadata, the privacy-policy site,
artwork metadata, documentation, packaging, deployment examples, tests, and historical
specification prose. Keep stable technical identifiers based on `telegram-tts-bot` where
a public brand is unnecessary.

## Context

The previous transliterated name is unclear to a native English speaker and is no longer
accepted for the product. The deployed bot already uses the descriptive username
`@TextToVoiceRuBot`, so the rebrand does not require a new bot or token. Telegram permits
owners to update names and localized profile text, but an ordinary bot's primary
username cannot be changed after creation.

This specification replaces only the inherited branding decisions. All accepted input,
speech, queue, privacy, localization, deployment, and delivery behavior remains in
force.

## Goals

- Present **Read Aloud** as the only product name in Russian and English interfaces.
- Keep runtime `/start` text and the canonical BotFather launch pack synchronized.
- Update the public privacy-policy site without changing its processing claims.
- Remove the retired name from source-controlled text, paths, assets, tests, and build
  metadata.
- Use descriptive technical identifiers for Docker resources and documentation paths.

## Non-goals

- Changing the existing `@TextToVoiceRuBot` username, bot token, repository name,
  Python package name, privacy-policy domain, avatar artwork, or product behavior.
- Redesigning the privacy site or avatar.
- Adding commands, locales, voices, persistence, or external services.

## User-visible behavior

The default and English display name is `Read Aloud - Text to Voice`. The Russian
display name is `Read Aloud - озвучивание текста`. English `/start` begins with
`Hi! This is Read Aloud.` and Russian `/start` begins with
`Привет! Это Read Aloud.` The remaining localized behavior stays equivalent.

The About text, full description, privacy-policy page, document metadata, and accessible
labels use the new name. The username and public policy URL remain unchanged.

## Design and interfaces

`telegram_tts_bot.localization` remains the runtime owner of bot messages, and
`specs/BOTFATHER.md` remains the canonical copy/paste launch pack. The privacy site keeps
its current layout and styling. The existing text-free avatar is retained under
`assets/read-aloud-avatar.svg` and `assets/read-aloud-avatar.png`.

Operational examples use `telegram-tts-bot` for the image, container, installation
directory, and license-document path, plus `ttsbot` for the unprivileged runtime user.
No Python import or entrypoint changes.

Historical specifications retain their decisions and status but use the current product
name so the retired name does not remain in repository search results.

## Configuration, security, and privacy

No token, setting, data flow, retention rule, or trust boundary changes. The privacy
policy's current disclosures remain intact. Rebranding does not require token rotation.

## Failure cases

- If localized Telegram profile fields are not all updated, some clients may keep showing
  the old localized name or description even after the default field changes.
- If the public privacy site is not deployed, the canonical source and live policy will
  temporarily differ.
- Username candidates are not offered as an in-place migration because Telegram does not
  permit changing the existing primary username.

## Acceptance criteria

- Case-insensitive repository search finds no source occurrence or source filename using
  the retired English or Russian brand.
- Russian and English runtime `/start` copy use **Read Aloud** and match the launch pack.
- The privacy site renders **Read Aloud** in its title, visible identity, policy text,
  footer, and asset references.
- Docker and deployment examples contain no retired brand identifier.
- The existing username and privacy-policy URL remain unchanged.
- Locked Ruff lint, Ruff format, strict mypy, pytest, privacy-site lint, build, and tests
  pass.

## Test plan

- Update exact localization and package metadata assertions.
- Build and server-render the privacy site, asserting the new title and absence of the
  retired name.
- Search source-controlled and unignored files and paths for the retired name.
- Run the complete required local checks.

## Delivery and rollback

Deploy the privacy-site update and restart the bot after applying the source change.
Manually update every default, English, and Russian BotFather profile field listed in the
launch pack. Runtime `/start` and `/help` copy ships with the bot deployment rather than
through BotFather. The username and token stay in place. Rollback restores the previous
source, site version, and BotFather profile copy; no data migration exists.

## Alternatives

`Spoken`, `Say It`, and a purely descriptive `Text to Voice` name were considered.
**Read Aloud** was selected because it is idiomatic English and communicates the action
immediately without inventing a new word.

## Open questions

None.
