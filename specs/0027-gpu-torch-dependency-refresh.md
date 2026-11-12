---
id: "0027"
title: GPU Torch dependency refresh
status: implemented
created: 2026-11-12
updated: 2026-11-12
supersedes: ["0025"]
---

# SPEC-0027: GPU Torch dependency refresh

## Contract

Supersede only SPEC-0025's GPU Torch pin: use torch 2.14.0+cu130 with its locked
CUDA dependencies. Preserve CPU torch 2.13.0+cpu and GPU torchaudio 2.11.0+cu130.
All other SPEC-0025 contracts remain in force, including Python 3.14, runtime
isolation, model identities, rendering, public interfaces and deployment gates.
The independent Qwen package refresh in SPEC-0026 may be combined with this update.
Update the GPU final-image assertion to check the new exact version.

## Acceptance

- The locked lint, formatting, strict mypy and fake-test checks pass.
- CPU and GPU container CI pass, including real backend imports and offline Silero
  rendering. GPU inference remains dependent on suitable GPU hardware.
- Preserve the official CPU and CUDA indexes, hashed artifacts, and exclusive extras.
- Merge only after the updated PR head passes CI.

## Implementation

Implemented in [840ef94](https://github.com/ihoru/telegram-tts-bot/commit/840ef94a6e41e976b8d79de6e63be58224fc3671).
The combined locked Ruff, formatting, mypy and fake-test checks pass with 239 tests
passed and eight skipped. Container CI is the merge gate; publication, deployment
and real Qwen GPU inference remain separate verification states.

## Open questions

None.
