# CPU-only Silero runtime plan

Status: local implementation and verification complete; publication and production
rollout pending. Created 2026-11-12 for `~/projects/my/telegram-tts-bot/`.
Contract: [SPEC-0025](specs/0025-cpu-only-silero-runtime.md).
Evidence: [local verification record](docs/cpu-runtime-verification.md).

## Goal

Ship a reproducible CPU-only image for the Silero deployment on `iho.su`, removing
unused CUDA dependencies while preserving voice, output, queue behavior, privacy,
and the separately supported Qwen GPU runtime.

## Verified baseline

- The live container is `telegram-tts-bot`, using Silero `xenia` with
  `TTS_MAX_CONCURRENCY=1`. It has no model/data mounts and no visible NVIDIA device;
  `torch.cuda.is_available()` returned false.
- Its image is 6.21 GB. Installed dependencies occupy 5.2 GiB, including 2.7 GiB
  under `nvidia/`, 689 MiB of Triton, and 1.1 GiB of Torch.
- Production uses `torch==2.13.0+cu130`. Both the local and server source trees
  explicitly select the CUDA 13.0 index for Torch and torchaudio in `pyproject.toml`.
- Official CPU indexes currently list CPython 3.14 Linux x86_64 wheels for
  `torch==2.13.0+cpu` and `torchaudio==2.11.0+cpu`. Wheel availability alone does not
  establish that these versions resolve together; validate wheel metadata and the lock.
- The server checkout differs from the running image revision. Reconcile the intended
  source revision with the deployed immutable image before any build or rollout.
- Cleanup is already complete: unused Docker images/cache and the old stopped TTS
  rollback were removed. Disk usage fell from 91% to 27%, freeing about 37 GiB.
  Journals now have `SystemMaxUse=512M`, `SystemKeepFree=1G`, and 14-day retention.

## Implementation sequence

1. **Record the contract.** Read `AGENTS.md`, `specs/README.md`, SPEC-0008,
   SPEC-0022, and SPEC-0023. Draft the next available numbered specification
   (0024 already exists locally); explicitly preserve Qwen GPU support and describe
   the CPU flavor, image naming, default voice, deployment selection, and checks.
   Accept it under the repository workflow before implementing. Preserve existing
   untracked `privacy-site/` and `specs/0024-failure-isolated-update-logging.md` work.

2. **Separate dependencies.** Introduce a CPU/Silero dependency selection and retain
   the existing Qwen/CUDA selection. Use the official CPU wheel index explicitly;
   regenerate and verify `uv.lock`, including hashes and Python 3.14/amd64 resolution.
   Validate Torch/torchaudio compatibility rather than forcing incompatible versions.
   Install only dependencies needed for Silero in its image; keep Qwen-specific
   packages and their transitive GPU dependencies in the GPU selection. Check current
   uv documentation before choosing extras, conflicts, or per-profile lock strategy.

3. **Make CPU startup independent.** `src/telegram_tts_bot/speech/factory.py` currently imports the Qwen
   adapter unconditionally, and that adapter imports NumPy and soundfile. Check all
   startup/CLI import paths before removing Qwen dependencies; select/import adapters
   only where needed. A CPU image configured for Aiden/Serena must fail clearly with
   content-free diagnostics rather than silently changing voices. Preserve existing
   rendering and error contracts.

4. **Build a CPU flavor from a clean base.** Extend `Dockerfile` with explicit CPU
   build/test/runtime targets. Copy only the CPU environment into its final image;
   deleting CUDA files in a later layer of the old image will not reclaim those layers.
   Preserve UID/GID 10001, FFmpeg/SoX, the checksum-pinned Silero model, offline behavior,
   environment handling, and applicable license notices. Use a valid Silero default
   for the CPU image; preserve the deployed `xenia` override and concurrency of one.
   Keep existing GPU defaults and publication compatibility unless the new spec
   explicitly defines a migration.

5. **Verify and publish the exact CPU artifact.** Adapt
   `scripts/verify-runtime-image.sh` to verify both profiles: its current assertions
   require CUDA Torch, Qwen packages, and the `aiden` default. Update
   `.github/workflows/ci.yml` and `release.yml` to test and publish distinct immutable
   CPU/GPU artifacts. Use separate cache scopes and update third-party notices and
   deployment documentation. Inspect `scripts/deploy_server.py` and its tests so the
   existing SPEC-0023 deployment path selects the intended CPU digest without
   broadening SSH permissions or changing publication-versus-deployment rules.

6. **Roll out after verification.** Capture the current image digest and configuration
   securely, and retain that known-good image during migration. Pull the verified CPU
   digest; gracefully stop the old poller before starting the replacement with the
   existing root-only environment, logging, restart policy, voice, and concurrency.
   Verify startup, one real Telegram voice reply, and absence of polling conflicts.
   Roll back on any failure. Prune the migration rollback and temporary build cache
   only after the CPU deployment is accepted.

## Acceptance checks

- Run the required locked Ruff check, Ruff format check, mypy, and pytest commands
  from `AGENTS.md`; validate workflow/shell changes using existing project checks.
- Assert in the exact final CPU image that `torch.version.cuda is None`, no
  `nvidia-*`, CUDA toolkit/bindings, or Triton distributions/libraries are installed,
  and application and CLI startup imports succeed with Qwen dependencies absent.
- Use the documented integration/stress markers: real Silero startup, xenia rendering,
  Russian and mixed-language input, OGG/Opus output at 48 kHz mono, and the existing
  two-render stress baseline under two CPUs and 1 GiB RAM. Preserve current latency,
  memory, chunking, cancellation, and failure expectations.
- Retain GPU dependency/import checks and the documented real Qwen verification where
  a suitable GPU is available. Do not claim CUDA inference was tested on `iho.su`.
- Measure uncompressed final-image bytes and dependency sizes against the 6.21 GB
  baseline; target at least 3 GB less without weakening runtime checks. Record actual
  results rather than estimating savings from package sizes alone.
- After authorized deployment, verify the running image digest, bot response, and
  `df`/Docker usage; record local, CI, published, and deployed states separately.

## References

- https://download.pytorch.org/whl/cpu/torch/
- https://download.pytorch.org/whl/cpu/torchaudio/
- https://pytorch.org/get-started/locally/
- Repository: `pyproject.toml`, `uv.lock`, `Dockerfile`, `src/telegram_tts_bot/speech/factory.py`,
  `scripts/verify-runtime-image.sh`, `scripts/deploy_server.py`, CI/release workflows,
  `DEPLOYMENT.md`, and specifications cited above.
