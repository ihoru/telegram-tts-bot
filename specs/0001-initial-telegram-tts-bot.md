---
id: "0001"
title: Initial Telegram TTS bot
status: implemented
created: 2026-08-27
updated: 2026-08-27
supersedes: null
---

# SPEC-0001: Initial Telegram TTS bot

## Summary

Build Vslukh, an independently extractable Python 3.14 Telegram bot that turns private
text messages, including forwarded text messages, into Russian OGG/Opus voice notes.
Speech generation is local and replaceable at a narrow code seam. The runtime retains
neither messages nor generated audio.

## Context

The repository begins as a standalone directory inside the current workspace. It must
be pleasant to operate and maintain: uv owns the environment and lockfile, Ruff owns
formatting and lint, mypy is strict, pytest enforces branch coverage, pre-commit gates
each non-bootstrap commit, and GitHub Actions verifies every push and pull request.

This is an ordinary BotFather bot. It is intentionally public because ordinary bots do
not have a BotFather friends-only private-message allowlist. Telegram managed-bot mode,
application access control, and a second manager bot are outside v1.

## Goals

- Convert every eligible private `Message.text` to one Russian Telegram voice note.
- Treat ordinary and forwarded text identically and ignore forwarding metadata.
- Supply a production-identical stdin-to-OGG executable for direct TTS testing.
- Keep the speech engine replaceable without a runtime provider framework.
- Ship reproducible local, container, CI, and tagged-release workflows.
- Provide exact professional BotFather metadata and a circle-safe avatar.

## Non-goals

- Persistence, queues, databases, caches, webhooks, multiple replicas, or a health API.
- Groups, channels, captions, media transcription, language detection, or multiple voices.
- Cloud TTS, provider discovery, runtime backend selection, or model downloads at runtime.
- PyPI publication, Docker Compose, host deployment, Mini Apps, payments, or inline mode.

## User-visible behavior

The bot runs as one long-polling process and preserves pending Telegram updates across
restarts. It accepts private chats only. `/start` and `/help` are commands; every other
non-empty private text message up to 4,096 Unicode code points is TTS input. No language
detection is performed: the Russian voice attempts all accepted text.

A forwarded text message follows the same path and speaks only `message.text`. The bot
does not inspect or narrate `forward_origin`, the author, or the source chat. Forwarded
captions and every other unsupported media type receive localized guidance. Group
updates are ignored.

The response is one mono 48 kHz OGG/Opus voice note encoded at 32 kbps and sent as a
reply to the input. Commands and failures return localized Russian for a `ru*` Telegram
language code and English otherwise, including when the code is absent. Exact `/start`,
`/help`, BotFather, and avatar content lives in `BOTFATHER.md`.

Overload is rejected immediately, without an application queue. The defaults are five
active synthesis-and-encoding pipelines globally and one per Telegram user. A global
or per-user limit has a distinct localized retry response. The global slot remains held
until encoding finishes, then releases before Telegram upload. Cancellation does not
release a slot while its worker is still running.

## Design and interfaces

The installed runtime command is `uv run python -m telegram_tts_bot`. aiogram 3 owns
Telegram routing and long polling. Workflow-data dependency injection supplies services
to handlers, so handlers import neither Piper nor FFmpeg.

The generic speech API is:

```python
@dataclass(frozen=True, slots=True)
class WavAudio:
    data: bytes


@dataclass(frozen=True, slots=True)
class VoiceAudio:
    data: bytes
    filename: str = "voice.ogg"
    mime_type: str = "audio/ogg"


class WaveSynthesizer(Protocol):
    def synthesize(self, text: str, /) -> WavAudio: ...


class VoiceRenderer:
    async def render(self, text: str, /) -> VoiceAudio: ...
```

`PiperWaveSynthesizer` is the sole production adapter. `VoiceRenderer` validates
non-empty text and owns the reusable synthesis-to-encoding pipeline. The FFmpeg encoder
is an internal injected test seam. Both blocking stages run as one job in a dedicated
executor: five workers in the bot and one in the CLI. A future engine implements
`WaveSynthesizer` and changes the composition factory; there is no registry, plugin
discovery, provider environment variable, or model-selection UI.

The model is `ru_RU-denis-medium` at piper-voices revision
`39ab474be869e9181350af6a65e4953eef67aaa0`:

- ONNX SHA-256: `15fab56e11a097858ee115545d0f697fc2a316c41a291a5362349fb870411b0a`
- JSON SHA-256: `831c860dac0b5073eaa81610a0a638ec23d90a6cf8e5f871b4485c2cec3767c8`

One model is loaded per process. A deliberate provisioning helper downloads and verifies
the pinned files into ignored `.models/piper/`. Bot startup and synthesis never download.
The container bakes and verifies the same assets. Generic speech types do not know Piper
paths or metadata.

Errors derive from `VoiceRenderError`: `InvalidTextError`, `SynthesisError`, and
`EncodingError`. Error values and logs never contain source text.

The installed `tts-to-ogg FILE [--force]` command reads strict UTF-8 from stdin only,
rejects empty or whitespace-only input, and imposes no character limit. It requires an
existing parent directory, refuses an existing destination without `--force`, and always
writes OGG/Opus regardless of suffix. It validates input and path before model loading.
Rendering completes before the destination is touched; forced replacement uses a sibling
temporary file and atomic replace. Success prints only the resolved output path. Exit
codes are 0 success, 2 usage/input/path/overwrite, 1 model/FFmpeg/synthesis/write, and
130 interrupt. The command requires no Telegram token.

## Configuration, security, and privacy

- `TELEGRAM_BOT_TOKEN`: required for the bot only.
- `PIPER_MODEL_PATH`, `PIPER_CONFIG_PATH`: optional local asset overrides.
- `TTS_MAX_CONCURRENCY`: positive integer, default 5.
- `TTS_MAX_CONCURRENCY_PER_USER`: positive integer, default 1 and no greater than global.
- `LOG_LEVEL`: standard logging level, default `INFO`.

Configuration is immutable after startup. `.env.example` contains placeholders only;
the application reads the process environment and does not silently load secret files.
Logs may contain event type, character count, durations, output byte count, and exception
class, but never tokens, message text, names, usernames, or forwarding data.

The bot creates no runtime files. WAV and OGG stay in memory and are released after the
Telegram upload attempt. CLI output is explicitly user-requested; its sibling temporary
file is cleaned after success, error, or interruption.

## Failure cases

- Missing token, FFmpeg, model, config, or correct checksum fails bot startup.
- Invalid settings fail with a concise message that does not expose secret values.
- Empty renderer input raises `InvalidTextError`; bot and CLI apply their own length rules.
- Piper and FFmpeg failures map to stable localized bot errors or CLI exit 1.
- Output-path validation happens before the CLI loads the model.
- Unsupported Telegram content receives guidance; group traffic receives no response.
- Telegram upload failures are logged without content and are not persisted or replayed.
- Shutdown stops intake, awaits active workers, closes the bot session, and releases assets.

## Acceptance criteria

- Direct and forwarded private text produce valid reply voice notes with identical text
  passed to the renderer.
- `tts-to-ogg` consumes stdin and produces production-identical OGG/Opus output.
- Five simultaneous pipelines complete in a two-CPU, 1 GiB container without OOM; timing
  and peak RSS are recorded without a latency threshold.
- Unit/component tests reach at least 90% branch coverage; lint, format, and strict types pass.
- Every non-bootstrap commit runs pre-commit pytest; every push and PR runs independent
  lint, test, and model/container integration jobs.
- A matching semantic-version tag publishes a non-root linux/amd64 GHCR image, GitHub
  release, SBOM, and provenance, but does not deploy to a host.
- No committed file or emitted log contains a real token, user text, or generated audio.

## Test plan

- Renderer: exact text, data types, call order, worker-thread execution, error mapping,
  cancellation, cleanup, and content-free diagnostics.
- Piper: explicit assets, checksum failures before load, valid in-memory WAV, no network
  during synthesis, and five-way shared-model stress.
- Telegram: commands, locale selection, direct/forwarded/privacy-hidden/copied text,
  group ignore, caption/media guidance, reply voice upload, capacity races, and failures.
- CLI: installed entry point, strict UTF-8, unlimited length policy, empty input, paths,
  overwrite and force, atomic cleanup, exit codes, and resolved-path stdout.
- Integration: ffprobe confirms OGG, Opus, mono, and 48 kHz; Docker runs non-root with
  FFmpeg and verified model assets.

## Delivery and rollback

The project uses Python `>=3.14,<3.15`, a committed uv lock, a multi-stage linux/amd64
image, and semantic tags beginning at `v0.1.0`. CI runs on every push and pull request.
The release workflow reruns verification before publishing version, SHA, and `latest`
GHCR tags. Rollback means redeploying a previous immutable image tag; there is no data
migration or persistent state to reverse.

## Implementation record

Implemented on 2026-08-27 by:

- `665b6da` — Python toolchain, lockfile, pre-commit, and local quality gates.
- `e44cb55` — replaceable speech renderer, pinned Piper adapter, and stdin CLI.
- `9b7c79a` — Telegram runtime, forwarding behavior, concurrency, and shutdown.
- `629c73b` — documentation, immutable container, CI, and release automation.

Verification completed with 79 passing tests and one skipped opt-in real-model test,
92.84% branch coverage, Ruff lint and format checks, strict mypy, locked package builds,
and a non-root production-image audit. The real model also completed the five-render
two-CPU/1 GiB stress scenario and produced verified mono 48 kHz OGG/Opus output. No
release tag was created as part of implementation.

## Alternatives

- A managed Telegram bot could restrict access but requires a separate privileged manager
  bot and a different creation flow; ordinary public BotFather setup was selected.
- A user-ID allowlist would provide application authorization but requires configuration
  and changes the selected public behavior.
- A provider registry and runtime backend switch add maintenance without a second provider.
- Model-per-worker isolation increases memory beyond the target host; a shared model plus
  constrained real stress coverage is selected.
- Queuing improves burst handling but needs lifecycle, fairness, and shutdown policy; v1
  rejects overload immediately.

## Open questions

None.
