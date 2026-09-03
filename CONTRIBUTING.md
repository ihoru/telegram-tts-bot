# Contributing

Thank you for improving Read Aloud. The project favors small, evidence-backed changes and a
stable maintenance surface over feature breadth.

## Start with the contract

Read `AGENTS.md`, [the specification index](specs/README.md), and every active
specification related to your change.

A new numbered specification must be accepted before implementing a change to:

- user-visible bot behavior or localization;
- the CLI contract;
- TTS engines, models, or output encoding;
- concurrency, persistence, privacy, or security boundaries;
- deployment or release behavior;
- BotFather metadata or branding.

Copy `specs/TEMPLATE.md`, use the next stable `NNNN-kebab-title.md` identifier, and leave
the status as `draft` while questions remain. Do not rewrite an implemented decision;
supersede it with a new specification. Pure bug fixes that restore an existing accepted
contract should reference that contract and include a regression test.

## Set up the repository

The supported development platform is Linux x86-64 with Python 3.14, uv, FFmpeg, and
SoX. Real Qwen inference additionally needs an NVIDIA BF16-capable GPU.

```bash
uv sync --locked --all-groups
uv run pre-commit install
```

For a one-time in-place migration from the former `qwen-tts` distribution, run
`uv sync --locked --all-groups --reinstall-package qwen-tts-hf`. Both distributions
provide the same `qwen_tts` import path, so uninstalling the former package can remove
files installed by its replacement. Fresh environments use the ordinary sync command.

Unit tests use fakes and do not need real models. Provision only the provider needed for
integration work. Qwen provisioning reports human-readable per-file download sizes on
stderr and handles Ctrl+C with exit status 130 and staging cleanup:

```bash
uv run python -m telegram_tts_bot.speech.qwen_model
uv run python -m telegram_tts_bot.speech.model --output-dir .models/silero
```

Long Qwen `tts-to-ogg` renders report content-free model-load and 500-character chunk
progress on stderr. They remain sequential and may take minutes without FlashAttention.
For local use, `bin/run_bot` and `bin/tts` enter the repository and select the locked uv
environment automatically. The Python entrypoints load only the repository-root `.env`
and never override variables already present in the process.

Never commit `.env`, `.models`, arbitrary generated OGG/WAV files, Telegram updates, or
logs that contain user data. The only audio exception is immutable, manifest-listed
synthetic comparison evidence under `auditions/`; follow SPEC-0006 and run its archive
test before adding a result.

## Make a focused change

- Keep Telegram concerns in handlers, admission policy in the bot service, speech behind
  `WaveSynthesizer`, encoding in the renderer, and construction in composition.
- Keep handlers and the CLI independent of Qwen, Silero, and FFmpeg implementation
  details.
- Do not add runtime downloads, persistence, queues, provider registries, or deployment
  machinery without an accepted specification.
- Preserve exact user input through the renderer and never include it in logs, exceptions,
  snapshots, or test names.
- Add focused tests for success, validation, failure, cancellation, and cleanup paths.

## Run the quality gate

Before opening a pull request, run:

```bash
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy src tests
uv run --locked pytest
uv build
uv run pre-commit run --all-files
```

Pytest enforces at least 90% branch coverage. Tests marked `integration` require system
dependencies or real model assets; tests marked `stress` exercise the constrained
Silero two-render path. The checked-in audition archive is validated offline but never
regenerated in CI. Keep ordinary tests deterministic and network-free.

Pre-commit intentionally runs Ruff with fixes. If it changes files, inspect them, stage
them yourself, and rerun the commit. Hooks must never invoke `git add`.

## Pull requests

A reviewable pull request:

- links its accepted specification or explains which existing contract it restores;
- describes observable behavior and relevant failure paths;
- includes tests at the narrowest responsible layer;
- passes all CI jobs independently;
- updates README, security, third-party, or BotFather material when those facts change;
- contains no secrets, downloaded models, unlisted generated audio, or user text.

Keep commits cohesive and green. A typical feature sequence is specification, tool or
interface support, behavior and tests, then operational/documentation polish. Maintainers
may squash during merge, but each local commit should pass pre-commit after the initial
repository bootstrap exception described by SPEC-0001.

## Releasing

Releases are repository-owner operations:

1. Ensure `main` is green and the accepted specifications reflect the release.
2. Set the static version in `pyproject.toml` and refresh `uv.lock`.
3. When updating the Python base digest, move `docker/debian.sources` to a reviewed
   immutable snapshot from the same date and rebuild the runtime integration image.
4. Create and push an annotated `vX.Y.Z` tag whose value exactly matches that version.
5. Let the release workflow rerun quality and constrained stress checks.
6. Verify the GitHub release, GHCR digest, SBOM, and attestations.

The workflow publishes artifacts only. Deploying a released image is a separate,
explicit operator action.
