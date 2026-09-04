---
id: "0023"
title: Publish-only deployment bootstrap and access verification
status: accepted
created: 2026-09-04
updated: 2026-09-04
supersedes: "0022"
---

# SPEC-0023: Publish-only deployment bootstrap and access verification

## Summary

Extend SPEC-0022 with manual CI publication on main without container replacement.
This allows creating the GHCR package and verifying restricted SSH before enabling
deployment. Preserve SPEC-0022's server command, rollback, and push deployment rules.

## Contract

- `workflow_dispatch` on main runs the normal lint, tests, container integration,
  and runtime verification, then publishes the exact image independently of
  `DEPLOY_ENABLED`. Manual runs on other branches never publish or access production.
- Manual main runs additionally verify the production SSH secrets from a GitHub
  runner. The forced command must reject `check` with the known validation message
  and exit code 1; connectivity or permission failures fail this check.
- Only a push to main with `DEPLOY_ENABLED=true` can replace the running container.
  A manual invocation never deploys, even when that variable is enabled.
- The shared SSH client setup enforces the same host pinning, input validation,
  temporary credential permissions, and cleanup for deployment and access checking.

## Server bootstrap

The user authorized setup on iho.su and public GHCR images. Preserve the existing
container while installing the root-owned server script and limited deployment user.
Recover only current environment overrides relative to its image directly on the
server, preserving the token and logging configuration. Pin the observed xenia voice
and concurrency of one explicitly in the root-only environment file.

Set up the main-only production environment, SSH secrets, and server variables while
deployment is disabled. Publish manually, make the new GHCR package public through
GitHub package settings, verify anonymous server pull access, then enable deployment.
The next feature push remains the first automatic replacement. Public images contain
the source and bundled models, never container runtime environment or user data.

## Verification and delivery

Run locked Ruff, format, mypy, pytest, workflow validation, and shell syntax checks.
Verify arbitrary commands and shell requests are rejected; verify SSH access from the
manual GitHub run. Compare the live container ID and start time before and after setup.
Commit only bootstrap changes, preserving the separate feature worktree edits.
Disabling `DEPLOY_ENABLED` stops future automatic deployments without affecting the bot.

## Open questions

None.
