# Vslukh

Vslukh is a local-first Telegram bot that turns regular and forwarded text messages into
Russian voice notes. The accepted v1 contract is
[SPEC-0001](specs/0001-initial-telegram-tts-bot.md); setup instructions will be completed
with the implementation.

The project requires Python 3.14 and [uv](https://docs.astral.sh/uv/):

```bash
uv sync --locked --all-groups
uv run pre-commit install
uv run pytest
```
