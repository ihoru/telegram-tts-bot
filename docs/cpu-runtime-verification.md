# CPU runtime verification — 2026-11-12

Local implementation of [SPEC-0025](../specs/0025-cpu-only-silero-runtime.md).
CI execution, registry publication and production rollout are still pending. No server
configuration, running production container or rollback image was changed or pruned.
SPEC-0025 remains accepted until an implementing commit/release is recorded.

## Final CPU artifact

- Target: `runtime-cpu`, tag: `telegram-tts-bot:cpu-check`, Linux amd64, Python 3.14.7.
- Local image ID: `sha256:e7a072f8c608f8ba05fe51f36e7750afb2f429e939aa31e46e3e835fc9bfcee8`.
  This is a local image ID, not a published registry manifest digest.
- Uncompressed image: **1,551,140,834 bytes**. `/app/.venv`: **822,282,301 bytes**.
- Retained local GPU baseline `vslukh:qwen-speedup`: **6,214,628,149 bytes**;
  its `/app/.venv`: **5,492,622,852 bytes**. The provided production plan recorded
  approximately 6.21 GB; production was not remeasured in this implementation run.
- Actual local image reduction: **4,663,487,315 bytes** (about 4.66 GB), exceeding
  the 3 GB target. Dependencies shrink by **4,670,340,551 bytes**.
- UID/GID 10001; defaults xenia and concurrency one; checksum-pinned Silero model;
  FFmpeg/SoX, license texts, and offline environment retained.

`scripts/verify-runtime-image.sh telegram-tts-bot:cpu-check cpu` passed, including
`torch==2.13.0+cpu`, `torch.version.cuda is None`, absent CUDA/NVIDIA/Triton
packages/libraries, absent Qwen/transformers/torchaudio/soundfile, startup/CLI imports,
and clear content-free errors for either Qwen voice. Offline xenia synthesis of the
script's synthetic Russian/English text produced Opus in OGG at 48 kHz, mono.
The recorded CLI render time was 0.462 seconds (excludes model load; not a benchmark
comparison with another runtime).

## Local checks

- Locked Ruff lint and format, strict mypy (43 files), pytest: **232 passed,
  8 skipped**, total coverage **91.24%**, host Python **3.14.10**. Skips are the six
  model/stress cases without configured model paths and two profile-specific package
  tests in the fake-only development environment.
- `uv lock --check` and `uv build` passed. Selecting both extras with a dry-run sync
  was rejected. The CPU CPython 3.14 amd64 Torch wheel has a SHA-256 in `uv.lock`;
  the GPU versions remain unchanged. CPU excludes unused torchaudio altogether.
- actionlint passed for both workflows; ShellCheck passed for changed shell files;
  deployment SSH shell syntax and `git diff --check` passed. The unchanged SSH script
  retains its existing SC2029 client-expansion note; its validated digest intentionally
  expands on the client.
- Final `test-cpu` image ID:
  `sha256:f017737eca8623764cf6491cb8801becdaf98861228a70af74413b192b823ad5`.
  Its fake suite: **233 passed, 1 skipped, 6 deselected**. Repository-only `bin/`
  launchers and immutable `auditions/` fixtures were mounted read-only; the integration
  image deliberately excludes them. An initial unmounted full-suite attempt failed
  only because those ten launcher/archive tests lacked their fixtures.
- CPU `integration and not stress`: **3 passed, 2 skipped** (Qwen model not mounted).
  Covers all Silero voices including xenia, maximum-length chunking, Latin/digits/
  punctuation and mixed-language input.
- CPU stress node passed with Docker **2 CPUs, 1 GiB RAM, no swap**, **8.35 s** wall
  time, GNU time max RSS **1,019,184 KiB**, cgroup peak **1,073,741,824 bytes**, exit 0.
  It completed at the configured cgroup memory ceiling; no additional memory headroom
  is claimed. Cgroup settings were independently confirmed:
  `cpu.max=200000 100000`, `memory.max=1073741824`, `memory.swap.max=0`.

## GPU and rollout boundaries

Actual imports of Torch 2.13.0+cu130, torchaudio 2.11.0+cu130 and
`faster_qwen3_tts.FasterQwen3TTS` succeeded in the retained GPU baseline environment.
The clean final `runtime` image
`sha256:5e993f4fefa5f7f18d2419453cc2cd58e753a52735a4355c3d12f1ce36189780`
is **6,214,933,931 bytes**, with **5,492,747,782 bytes** under `/app/.venv`.
`scripts/verify-runtime-image.sh telegram-tts-bot:gpu-check gpu` passed, including
actual imports of all three modules, CUDA 13.0 package metadata, aiden/concurrency-one
defaults, model/license checks and real offline Silero xenia OGG/Opus rendering.
The CPU image is **4,663,793,097 bytes** smaller than this freshly built GPU image.
Real Qwen CUDA inference could not run: the host reports `Failed to initialize NVML:
Driver/library version mismatch` (NVML library 620.70). No driver changes were made.
No CUDA inference on iho.su is claimed.

Before rollout, install the new root-owned deployment script, reconcile source and
running immutable revision, retain the known-good image and secure environment, publish
the verified CPU artifact, then follow [the migration procedure](../DEPLOYMENT.md).
Verify the running digest, one real Telegram voice reply, polling conflicts and server
Docker/filesystem usage before accepting deployment or pruning migration rollback.
