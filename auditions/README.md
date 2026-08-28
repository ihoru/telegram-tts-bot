# Voice audition history

This directory preserves comparable, checked-in WAV renders so voice quality can be
reviewed across engines, model revisions, and speakers without depending on temporary
files or Git history.

Each suite fixes one prompt and stores its exact UTF-8 SHA-256 in `manifest.json`. The
current prompt is 157 Unicode characters long; that is simply its character count, not
a model limit. Every result is mono, signed 16-bit PCM WAV produced at the synthesizer
boundary before FFmpeg converts bot output to OGG/Opus.

## Chronology

| Date | Suite | What was compared | Outcome |
| --- | --- | --- | --- |
| 2026-08-28 | [`mixed-ru-en-v1`](mixed-ru-en-v1/) | Piper 1.7.0 (3 voices), Silero `v5_5_ru` (5 voices), Qwen3-TTS 0.6B CustomVoice (3 voices) | Aiden selected as the default; Serena was retained as a configurable Qwen voice; the three selected Silero voices remain available. |
| 2026-08-28 | [`mixed-ru-en-v1`](mixed-ru-en-v1/) | Qwen3-TTS 0.6B Aiden with `qwen-tts 0.1.1` versus `faster-qwen3-tts 0.4.0` | The accelerated deterministic result became the bot default implementation; the official-runtime WAV remains as history. |

The machine-readable chronology, artifact hashes, source revisions, render parameters,
and individual decisions live in each suite manifest. Future comparisons must create a
new suite or append a new immutable result; never replace an existing WAV.

Run the archive integrity test after adding a result:

```bash
uv run --locked pytest tests/test_audition_archive.py
```
