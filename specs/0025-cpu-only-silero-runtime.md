---
id: "0025"
title: Separate CPU Silero and GPU Qwen runtimes
status: accepted
created: 2026-11-12
updated: 2026-11-12
supersedes: ["0008", "0023"]
---

# SPEC-0025: Separate CPU Silero and GPU Qwen runtimes

## Summary and preserved contracts

Add a reproducible CPU-only Silero image alongside the existing Qwen CUDA image.
This supersedes only SPEC-0008's single-image dependency contract and SPEC-0023's
single publication digest. Their inference, privacy, publication gates, restricted SSH,
startup verification, and rollback contracts otherwise remain in force. Voice synthesis,
chunking, queueing, cancellation, output, environment overrides and no persistence remain
unchanged. Existing unrelated SPEC-0024 and privacy-site work is outside this change.

## Dependencies and startup

Use mutually exclusive `cpu` and `gpu` project extras in one hashed uv lock, with explicit
official PyTorch CPU and CUDA 13.0 indexes. CPU includes Torch and NumPy for Silero;
Qwen, soundfile, transformers, torchaudio and their GPU dependencies belong only to GPU.
Keep the locked GPU versions. CPU pins Torch 2.13.0+cpu; no unused torchaudio is needed.
Development fakes may use NumPy and soundfile without an installed inference backend.
Local installation explicitly chooses `uv sync --locked --extra cpu` or `--extra gpu`;
launchers default to GPU for compatibility and accept `TTS_RUNTIME=cpu` to choose CPU.
The application default stays aiden; the CPU image sets TTS_VOICE=xenia and concurrency
one. Import Qwen only when selected; missing dependencies must produce a content-free
SynthesisError, without fallback or an import traceback containing application data.

## Images and publication

Keep `build`, `test`, `runtime` Docker targets and unsuffixed release tags as GPU aliases.
Add `build-cpu`, `test-cpu`, `runtime-cpu` targets from a clean shared Python base, copying
only the selected environment. Preserve pinned bases, model checksum, UID/GID 10001,
FFmpeg/SoX, offline settings and license notices. Label images `io.iho.tts.runtime=cpu|gpu`.
CI builds/tests/verifies both exact runtime images with separate cache scopes; it runs
CPU two-render stress under two CPUs and 1 GiB. Publish main-SHA-cpu and main-SHA-gpu,
retaining main-SHA as GPU compatibility alias. Release tags VERSION-cpu, SHA-cpu and
latest-cpu select CPU; existing VERSION, SHA and latest plus explicit -gpu aliases select
GPU. Attest and inventory each published profile without rebuilding after verification.
Manual main publication remains independent of DEPLOY_ENABLED and never deploys.

## Deployment and rollback

CI selects the CPU digest by default for the existing Silero production configuration;
DEPLOY_RUNTIME=gpu selects GPU for a Qwen server. Server config runtime=silero accepts
only a CPU-labelled image; runtime=qwen accepts only GPU. Validate after pull and before
stopping any poller. SSH still accepts only the existing repository digest command and
keeps the same privileges. Existing root-only environment must pin xenia and concurrency
one. Reconcile server source with the deployed immutable image before rollout, capture
its digest and configuration securely, pull before stopping, retain the previous image
and container, and start only after the old poller stops. Roll back on startup failure.
Verify a real Telegram reply and no polling conflicts before accepting migration;
pruning rollback images/cache is a later explicit operator action.

## Acceptance and verification

- Required locked Ruff, formatting, mypy and pytest checks pass with fakes.
- Both extras resolve for Python 3.14 Linux amd64 with hashes and compatible metadata;
  selecting both fails. GPU retains CUDA Torch and accelerated Qwen distribution checks.
- Exact CPU image has torch.version.cuda=None; no nvidia, Triton, CUDA toolkit/bindings,
  Qwen, transformers, soundfile or torchaudio packages/libraries. Bot and CLI imports
  succeed without Qwen dependencies; either Qwen voice fails clearly without fallback.
- Both exact runtime images pass model/license checks and offline Silero rendering;
  CPU real integration covers xenia, Russian/mixed text, maximum-length chunking and
  48 kHz mono OGG/Opus, plus the existing constrained two-render baseline.
- Measure final CPU image bytes and dependency bytes; target >=3 GB below the recorded
  6.21 GB GPU production baseline. Record measurements and unavailable checks honestly.
- Tests prove profile mismatch fails before downtime, existing rollback and SSH rejection
  remain intact. Validate workflows and shell syntax. Real Qwen inference requires a
  suitable GPU and is never inferred from CPU tests.
- Report local, CI, published and deployed states separately. Live rollout follows exact
  artifact verification; a local implementation does not imply publication or deployment.

## Alternatives

Separate lockfiles duplicate common dependency resolution. Removing CUDA files from a
GPU image retains its layers. Installing both profiles defeats the CPU size contract.

## Open questions

None.
