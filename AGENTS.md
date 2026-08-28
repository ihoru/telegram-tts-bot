# Agent guide

## Change workflow

Before changing user-visible bot behavior, CLI contracts, TTS providers or models,
concurrency, persistence, deployment, or BotFather metadata, read `specs/README.md`
and the active linked specifications. Create and accept a numbered spec before
implementing a new capability or changing an existing contract; supersede implemented
specifications instead of rewriting their decisions.

Keep v1 narrow: one private-chat polling bot, one startup-selected local Qwen or Silero
voice, one OGG renderer, and no persistence. Put Telegram concerns in handlers,
admission control in the bot service, synthesis behind `WaveSynthesizer`, and process
assembly in the composition module.

## Required checks

Use the locked uv environment. Before handing off a change, run:

```bash
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy src tests
uv run --locked pytest
```

Pre-commit may rewrite files with Ruff. Review and stage those edits yourself, then
rerun the commit; hooks must never stage files automatically.

Never commit tokens, downloaded model files, arbitrary generated audio, user text, or
logs that contain message content. The sole audio exception is immutable, manifest-
listed synthetic evidence under `auditions/`; follow `auditions/README.md` and
SPEC-0006 when changing it. Tests use fakes by default; run real-model and container
tests only through their documented markers or CI jobs.
