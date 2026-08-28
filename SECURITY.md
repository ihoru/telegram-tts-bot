# Security policy

## Supported versions

| Version | Support |
| --- | --- |
| Latest tagged release | Security fixes |
| Current `main` | Best-effort pre-release support |
| Older releases | Not supported |

Until the first tag, report issues against `main`.

## Reporting a vulnerability

Use GitHub's **Security → Report a vulnerability** private reporting flow when it is
enabled for the repository. If private reporting is unavailable, open a minimal public
issue asking the maintainer for a private contact channel. Do not include an exploit,
bot token, Telegram identifier, private message, voice sample, or other sensitive data in
that public issue.

Include, when safe:

- the affected version or image digest;
- the component and configuration involved;
- reproduction steps using synthetic data and a revoked/test token only;
- expected impact and any known mitigations.

The maintainer will acknowledge a complete private report, assess its severity, and
coordinate a fix and disclosure. No fixed response-time SLA is promised for this
personal, alpha-stage project.

## Security model

- `TELEGRAM_BOT_TOKEN` is the only bot credential. Supply it through the runtime
  environment or a deployment secret store, never a committed file or Docker build
  argument. Revoke it immediately with BotFather if exposure is suspected.
- Vslukh stores no Telegram messages or rendered audio. It keeps data in process memory
  only for rendering and upload. The CLI writes only the explicitly requested output.
- Logs omit message text, names, usernames, forwarding metadata, and token values.
- The Qwen adapter accepts exactly eleven pinned snapshot files and verifies every
  SHA-256 before importing the inference package. It uses local-only loading with Hugging
  Face and Transformers offline modes; the model uses safetensors rather than pickle.
- The Silero PyTorch package contains executable model code. Only the documented
  `v5_5_ru.pt` SHA-256 is accepted before deserialization, and runtime model downloads
  are disabled. Treat both model-path overrides as trusted deployment inputs.
- Release actions and container bases are pinned to immutable digests; tagged releases
  carry SBOM and provenance attestations.
- The runtime image uses an unprivileged user. Qwen deployments mount only the verified
  model directory read-only; neither provider needs a writable volume.

The bot is intentionally public. Disabling group joining and keeping group privacy on do
not authorize private-chat users. Anyone who discovers the username can use it. Do not
deploy this version when application-level access control is a requirement.

Telegram necessarily processes incoming messages and returned voice notes. Local speech
generation and the bot's no-persistence policy do not change Telegram's own data handling
or create end-to-end confidentiality.

## Operational hardening

- Run exactly one polling replica per token.
- Keep the host, Docker engine, base image, uv lock, and Dependabot updates current.
- Give the container only outbound network access needed for Telegram; it does not need
  inbound ports.
- Do not mount the Docker socket, source repository, or host secrets into the runtime
  container. Mount only the Qwen model directory, read-only, at its configured path.
- Keep Qwen concurrency at exactly one. The supported baseline is one BF16-capable
  NVIDIA GPU with 8 GiB VRAM and at least 8 GiB host RAM. A Silero-only deployment may
  use the separately measured default of two on a two-CPU, 1 GiB host.
- Roll back by redeploying a previously trusted immutable image digest.
