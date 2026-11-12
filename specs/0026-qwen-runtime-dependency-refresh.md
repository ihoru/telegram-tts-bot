---
id: "0026"
title: Qwen runtime dependency refresh
status: accepted
created: 2026-11-12
updated: 2026-11-12
supersedes: ["0025"]
---

# SPEC-0026: Qwen runtime dependency refresh

## Contract

Supersede only SPEC-0025's requirement to retain the GPU Qwen package version.
Use faster-qwen3-tts 0.5.4 with qwen-tts-hf 0.1.1.post1 in the GPU extra.
All other SPEC-0025 contracts remain in force, including CPU isolation, Python 3.14,
Torch versions, model identities, interfaces, voices, rendering and deployment gates.
Update the package assertion, final-image assertion and third-party package notice
with the pin. Do not weaken checks for the conflicting qwen-tts distribution.

## Acceptance

- The locked lint, format, mypy and fake-test checks pass.
- Both CPU and GPU container CI pass, including actual backend imports and offline
  Silero rendering; GPU inference remains dependent on suitable GPU hardware.
- Merge only after the updated PR head passes CI.

## Open questions

None.
