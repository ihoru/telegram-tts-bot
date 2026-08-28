---
id: "0004"
title: Configurable Silero voices
status: superseded
created: 2026-08-28
updated: 2026-08-28
supersedes: "0002"
superseded_by: "0005"
---

# SPEC-0004: Configurable Silero voices

## Summary

Replace the bundled Piper `ru_RU-denis-medium` voice with the Silero `v5_5_ru`
multi-speaker model. The operator selects one of the auditioned `kseniya`, `xenia`, or
`baya` speakers in immutable startup configuration. The bot still loads one local model
per process and exposes no user-facing voice selector.

This specification retains the bilingual welcome, privacy policy, Telegram behavior,
output format, persistence boundary, and delivery workflow accepted by SPEC-0002. The
additive record-voice behavior from SPEC-0003 also remains in force.

## Context

A blind listening comparison identified samples A, B, and F as the preferred voices.
The hidden mapping revealed them as `kseniya`, `xenia`, and `baya`, respectively. All
three are speaker IDs in one Silero model, so supporting them does not require three
model weights or a runtime provider registry.

The original Denis choice prioritized a CC0-backed source dataset, permissive model
distribution, a roughly 63 MiB model, and a reproducible local Piper deployment. It was
not selected through a listening comparison. The preferred Silero model is materially
larger and uses a non-commercial license, so its runtime and redistribution constraints
must be explicit.

## Goals

- Bundle one verified `v5_5_ru.pt` model containing all three preferred speakers.
- Let the operator select `kseniya`, `xenia`, or `baya` before startup.
- Preserve the existing engine-neutral `WaveSynthesizer` seam and OGG/Opus renderer.
- Remove the Denis model, Piper adapter, Piper dependency, and Piper configuration.
- Keep the supported two-CPU, 1 GiB deployment within a measured safe concurrency.
- Distribute the Silero weight with complete source, attribution, and license notices.

## Non-goals

- A Telegram command, button, or per-user preference for changing voices.
- Loading multiple model weights, changing speakers after startup, or provider discovery.
- Commercial or commercially advantageous use under the bundled model license.
- Persistence, a render queue, cloud synthesis, or runtime model downloads.
- Changes to Telegram routing, localized messages, BotFather metadata, or the privacy site.

## User-visible behavior

The bot speaks eligible private text with the single speaker selected when the process
starts. The three supported choices are:

- `kseniya` (blind sample A and the default);
- `xenia` (blind sample B);
- `baya` (blind sample F).

Changing `TTS_VOICE` and restarting the process changes the voice for all subsequent
messages. Users cannot select a voice in Telegram. All three choices still return one
mono 48 kHz OGG/Opus voice note at 32 kbps for the existing broad text-input contract.
Russian Cyrillic text is passed through unchanged. Latin letters are deterministically
transliterated, digits are read individually, and punctuation-only input speaks sign
names because the packaged Russian text cleaner otherwise drops or rejects that content.

## Design and interfaces

`SileroWaveSynthesizer` becomes the sole production `WaveSynthesizer`. It verifies the
model checksum before importing and loading the packaged PyTorch model, loads the model
once on CPU, and shares that immutable inference model across render workers. PyTorch
intra-operation threads are fixed at one so concurrent jobs do not multiply CPU threads.
Before serving traffic, the adapter runs one short, fixed, non-user warm-up phrase with
the configured speaker so the packaged model completes its lazy mutation before
concurrent calls begin.

The pinned model is `v5_5_ru.pt` from:

`https://models.silero.ai/models/tts/ru/v5_5_ru.pt`

Its SHA-256 is:

`50081637b602126ee06cb3bc8a744d25651d2da149ee8864b9a379bfdd934437`

The adapter uses the model's 48 kHz output and enables accent, `ё`, homograph-stress,
homograph-`ё`, and single-vowel stress handling. It converts finite normalized samples
to signed 16-bit mono PCM in an in-memory WAV. The existing FFmpeg stage produces the
unchanged Telegram OGG/Opus output.

The adapter preserves Cyrillic text, whitespace, and ordinary punctuation while making
Latin letters and Unicode digits speakable through deterministic Russian transliteration
and digit names. If an input still has no speakable Cyrillic content, punctuation is
named and otherwise unsupported symbols are identified by Unicode code point. This is a
compatibility fallback, not language-aware translation. Any expanded fallback text is
again partitioned to the model limit before inference.

Silero cannot synthesize the accepted 4,096-character Telegram maximum in one call. The
adapter therefore partitions long input into ordered chunks of at most 500 Unicode code
points, preferring a whitespace boundary when available. The chunks preserve all
non-whitespace content in order; whitespace-only spans are not sent as empty speech.
Each chunk is synthesized with the same speaker and parameters, and its PCM frames are
concatenated into one WAV before the unchanged single OGG encode. This remains an
internal provider constraint: the Telegram and CLI length contracts do not change.

The explicit provisioning helper downloads and verifies only the pinned `.pt` file into
ignored `.models/silero/`. Bot startup and synthesis never access the network. The
container bakes the same verified file at `/opt/silero/v5_5_ru.pt`.

The project uses the locked CPU-only PyTorch distribution from the official PyTorch CPU
package index on the supported Linux x86-64 AVX2 runtime. Unit tests use fakes and make
no network or real-model calls. Integration tests exercise the exact packaged model
separately.

## Configuration, security, privacy, and licensing

- `TELEGRAM_BOT_TOKEN`: unchanged and required for the bot only.
- `SILERO_MODEL_PATH`: optional model override; defaults locally to
  `.models/silero/v5_5_ru.pt`.
- `TTS_VOICE`: optional exact speaker ID; defaults to `kseniya` and accepts only
  `kseniya`, `xenia`, or `baya`.
- `TTS_MAX_CONCURRENCY`: positive integer, default 2.
- `TTS_MAX_CONCURRENCY_PER_USER`: unchanged default 1 and no greater than global.
- `LOG_LEVEL`: unchanged default `INFO`.

`PIPER_MODEL_PATH` and `PIPER_CONFIG_PATH` are removed rather than retained as aliases.
Configuration remains immutable after startup. Logs and exceptions identify only stable
failure classes and never include source text.

The unmodified Silero weight is a separately licensed component under Creative Commons
Attribution-NonCommercial-ShareAlike 4.0 International (CC BY-NC-SA 4.0). The repository
and container retain the model's source URI, creator attribution, any supplied copyright
notice, license text, and warranty disclaimer. Distribution and operation with this
bundled weight must be non-commercial; commercial deployment requires separate permission
from Silero. The application code remains under GPL-3.0-or-later, and this specification
does not claim that generated speech automatically inherits the model license.

The capacity default is based on real shared-model inference under a two-CPU, 1 GiB
no-swap cgroup with one PyTorch thread per call. Two simultaneous renders completed in
1.406 seconds with a cgroup peak of 837,464,064 bytes, leaving 225 MiB of cgroup
headroom. Three completed once with only about 16 MiB of cgroup headroom, while four and
five were OOM-killed before any call completed. Two is therefore the highest defensible
default for the supported host limit. Operators may raise it only after measuring their
own deployment limit. A production-matched follow-up with warm-up, NumPy conversion, and
two simultaneous maximum-size 500-codepoint chunks also passed: 3.156 seconds wall time,
813,772,800 bytes cgroup peak, and 259,969,024 bytes of headroom.

## Failure cases

- A missing, unreadable, or checksum-mismatched model fails before deserialization.
- An unsupported `TTS_VOICE` fails configuration with the allowed stable identifiers.
- A model import, package load, inference, invalid sample tensor, or WAV conversion error
  maps to `SynthesisError` without input-derived details.
- Non-finite or non-one-dimensional audio is rejected rather than encoded.
- Any failed long-text chunk fails the whole render; no partial voice note is returned.
- Existing FFmpeg, Telegram, overload, cancellation, and shutdown behavior is unchanged.
- Using the bundled model commercially violates its license unless separate terms apply.

## Acceptance criteria

- `kseniya`, `xenia`, and `baya` each synthesize through one verified shared model.
- Configuration selects exactly one speaker at startup and rejects every other value.
- Unit tests prove checksum-before-load, exact inference parameters, PCM WAV conversion,
  lossless long-text segmentation, mixed/non-Cyrillic compatibility, error privacy,
  configuration wiring, and provisioning cleanup.
- The real model loads and synthesizes on the supported Python 3.14 CPU runtime.
- The supported concurrency completes in a two-CPU, 1 GiB no-swap container without OOM,
  and the measured peak memory and timing are recorded.
- `tts-to-ogg` and the bot produce verified Opus, mono, 48 kHz output.
- Piper code, dependency, notices, environment variables, tests, and local Denis assets
  are absent after migration.
- Locked Ruff lint/format, strict mypy, and pytest checks pass.

## Test plan

- Adapter unit tests use fake torch/model/tensor objects to cover verification, loading,
  fixed warm-up, all three speakers, exact model flags, bounded long-text chunks, joined
  PCM, valid WAV output, and privacy-safe failures.
- Configuration and composition tests cover defaults, all supported values, invalid
  values, bot wiring, and CLI wiring without requiring a Telegram token.
- Provisioning tests cover verified reuse, atomic download, checksum mismatch, and cleanup.
- An opt-in real-model test renders every supported speaker plus the 4,096-character
  Telegram maximum, Latin-only, digit-only, punctuation-only, and mixed content, then
  validates the output.
- A constrained integration job uses two simultaneous renders with two CPUs, 1 GiB RAM,
  and no swap, then probes the encoded output.
- The runtime-image audit verifies the model checksum, environment, license material,
  non-root execution, installed CPU PyTorch build, FFmpeg, and end-to-end rendering.

## Delivery and rollback

The replacement removes the ignored local `.models/piper/ru_RU-denis-medium.onnx` and
matching JSON after the Silero path is ready. Existing deployments must set `TTS_VOICE`
only when they want a non-default preferred speaker; stale Piper path variables have no
effect. A new container image includes only the Silero weight.

Rollback means deploying the previous immutable Piper image. A local rollback must run
the previous revision's explicit Piper provisioner because the Denis files are removed.
There is no data migration or persistent user state.

## Alternatives

- Keeping Denis avoids the non-commercial restriction and uses less memory, but it is
  the voice explicitly rejected in the listening comparison.
- Bundling three separate Piper models would be more permissively licensed but would not
  provide the three selected voices, which belong to Silero.
- A runtime voice command adds user state and product surface that the operator did not
  request; immutable configuration is sufficient.
- Loading a model per worker multiplies memory beyond the deployment target; one shared
  model remains the required architecture.

## Implementation record

Implemented by `6cc06a5`. Verification completed with locked Ruff lint and format
checks, strict mypy, 117 passing tests with four opt-in tests skipped, real synthesis
for all three configured speakers, and a real 4,096-character chunked render. SPEC-0005
later superseded the single-provider/default-speaker decision while retaining Silero as
an available local provider.

## Open questions

None.
