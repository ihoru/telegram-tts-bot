---
id: "0022"
title: Main branch Docker deployment over restricted SSH
status: accepted
created: 2026-09-04
updated: 2026-09-04
supersedes: null
---

# SPEC-0022: Main branch Docker deployment over restricted SSH

## Summary

Deploy the exact verified production image after a push to main passes CI. Keep the
existing single-container `docker run` deployment and server-local bot configuration.
The user authorized repository setup; server provisioning and the first live test
remain operator steps, to be exercised with the next feature.

## Design and interfaces

- Extend CI: the container job waits for lint and tests, verifies its runtime image,
  then publishes that same image to GHCR under the full commit SHA. Publishing and
  deployment require repository variable `DEPLOY_ENABLED=true` and a push to main.
- The production deployment job receives the published digest, serializes deployments
  without cancelling an active deployment, and skips a commit no longer at main HEAD.
- SSH sends only `deploy sha256:<64 lowercase hex characters>`. A forced command
  invokes a root-owned Python 3 script via narrowly scoped sudo. The deployment user
  has no Docker group membership. The script allows only this repository's GHCR image.
- Root-owned JSON configuration selects Silero or Qwen and an environment file.
  Qwen preserves its read-only model mount and selected GPU. No bot token enters CI.
- Pull before stopping; acquire a server lock; stop the existing container with a
  600-second grace period, rename it as the previous container, and start the new one.
- Wait up to 600 seconds for `bot_polling_started`, with no restarts, then require
  another ten seconds of uninterrupted running. Logs are inspected but never printed
  by automation. This is a startup check, not proof of successful voice delivery.
- On replacement or startup failure, remove the failed container before restoring
  the previous container. Retain the stopped previous container after success for
  manual rollback. Refuse an ambiguous state with only a previous container present.
- Ignore SSH hangup so an ordinary disconnect does not interrupt replacement. Handle
  termination by attempting rollback; SIGKILL/host failure requires operator recovery.

## User-visible behavior

Deployment briefly interrupts service. Existing SPEC-0010 shutdown behavior applies:
active work receives a grace period and queued work is not persisted. Exactly one
container polls the token. Domain, HTTP endpoint, and reverse proxy are unnecessary.

## Configuration, security, and privacy

Document `DEPLOY_HOST`, `DEPLOY_USER`, optional `DEPLOY_PORT`, `DEPLOY_SSH_KEY`, and
`DEPLOY_KNOWN_HOSTS`. Pin SSH host identity verified independently by the operator.
Use public GHCR pull access or a server-local read:packages credential for private
images. The deployment key can replace this application with images from its registry;
its permissions do not constitute a guarantee about the application image's behavior.
Deployment files, sudo policy, and authorized keys are root-owned. No automated prune.

## Acceptance criteria and test plan

- PRs, tags, disabled deployment, and failed CI never invoke production deployment.
- Test command rejection, pull failure without downtime, stop-before-start ordering,
  startup success, failed start/readiness rollback, and ambiguous backup rejection
  using fake Docker operations; no real bot or model is required.
- Run locked Ruff, formatting, mypy, and pytest. Validate workflow syntax when tooling
  is available. Live acceptance on the next feature checks its image revision and
  sends a private message to confirm voice delivery.

## Delivery and rollback

Install the script/config/key on the server and set GitHub configuration before
enabling deployment. Committing these files alone does not enable it. Disable the
repository variable to stop future deployments; use the documented previous-container
procedure to roll back. Retain existing release-tag publishing.

## Open questions

None.
