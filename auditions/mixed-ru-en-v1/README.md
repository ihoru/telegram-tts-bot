# Mixed Russian-English audition, version 1

This suite compares all locally auditioned voices with the same primarily Russian text,
including English terms, a short English phrase, and ordinary punctuation. The exact
prompt is in [`prompt.txt`](prompt.txt); its logical content excludes the file's final
newline and is protected by the manifest SHA-256.

Listen to the WAV files under `results/`, then use `manifest.json` to identify the exact
engine, model revision, speaker, render settings, decision, and chronology. The files
deliberately retain each engine's native sample rate. They are archival evidence, not
runtime assets, and are excluded from Python packages and container images.

## Result summary

| Engine | Voice | Decision |
| --- | --- | --- |
| Piper 1.7.0 | Denis | Former default; removed from the bot |
| Piper 1.7.0 | Dmitri, Irina | Auditioned; rejected |
| Silero `v5_5_ru` | Kseniya, Xenia, Baya | Retained as selectable Russian-first voices |
| Silero `v5_5_ru` | Aidar, Eugene | Auditioned; rejected |
| Qwen3-TTS 0.6B CustomVoice, `qwen-tts 0.1.1` | Aiden | Former default runtime result; retained as history |
| Qwen3-TTS 0.6B CustomVoice | Serena | Retained as a selectable Qwen voice |
| Qwen3-TTS 0.6B CustomVoice | Vivian | Auditioned; rejected |
| Qwen3-TTS 0.6B CustomVoice, `faster-qwen3-tts 0.4.0` | Aiden | Current default runtime result |
