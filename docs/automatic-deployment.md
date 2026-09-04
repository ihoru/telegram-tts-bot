# Deploy main automatically with docker run

CI verifies the exact runtime image, publishes it to GHCR, and sends its digest over
SSH to your server. The server pulls before stopping the existing container, checks
startup, and restores the old container if the replacement fails. A restart alone
would keep running the old image, so deployment replaces the container.

## 1. Install the server command

These commands assume Ubuntu/Debian, Docker at `/usr/bin/docker`, Python 3.10 or newer,
and your existing container named `telegram-tts-bot`. Run them using your normal
server administrator account from a checkout containing this change. You can instead
copy the two source files to the server using your normal administrator SSH access.

```bash
sudo useradd --create-home --shell /bin/sh tts-deploy
sudo chown root:root /home/tts-deploy
sudo chmod 755 /home/tts-deploy
sudo install -d -o root -g root -m 755 /home/tts-deploy/.ssh
sudo install -d -o root -g root -m 755 /etc/telegram-tts-bot
sudo install -o root -g root -m 755 scripts/deploy_server.py /usr/local/sbin/deploy-telegram-tts-bot
sudo install -o root -g root -m 600 docker/deploy.json.example /etc/telegram-tts-bot/deploy.json
```

The account must be new and have no Docker group membership or other sudo privileges.
On subsequent script upgrades, repeat only the script installation; retain your config.
The dedicated user's home and SSH files are root-owned so it cannot replace the forced
command with a normal shell. Public authorized keys remain readable by that account.

Edit `/etc/telegram-tts-bot/deploy.json` with `sudoedit`. For CPU Silero:

```json
{
  "runtime": "silero",
  "env_file": "/opt/telegram-tts-bot/.env"
}
```

Keep your existing `.env`, including `TELEGRAM_BOT_TOKEN`, voice, and concurrency.
For example, xenia uses `TTS_VOICE=xenia` and `TTS_MAX_CONCURRENCY=2`.
The Docker image defaults to Qwen, so a Silero voice must be explicit in `.env`.
Protect it with `chmod 600`; the deployment user must not be able to modify it or
its parent directory. The root-owned deployment command reads it for Docker.

For Qwen use:

```json
{
  "runtime": "qwen",
  "env_file": "/opt/telegram-tts-bot/.env",
  "model_directory": "/opt/telegram-tts-models/qwen3-tts-12hz-0.6b-customvoice",
  "gpu": "device=0"
}
```

Keep your existing provisioned model, NVIDIA setup, and Qwen concurrency of one.
The new container uses the flags from DEPLOYMENT.md: init, restart unless-stopped,
600-second shutdown timeout, and local log rotation. If your current `docker run`
has additional resource limits or mounts, incorporate those into the root-owned
script before enabling deployment. No ports are exposed.

Allow sudo for only this script:

```bash
printf '%s\n' 'tts-deploy ALL=(root) NOPASSWD: /usr/local/sbin/deploy-telegram-tts-bot' | sudo tee /etc/sudoers.d/telegram-tts-bot-deploy >/dev/null
sudo chmod 440 /etc/sudoers.d/telegram-tts-bot-deploy
sudo visudo -cf /etc/sudoers.d/telegram-tts-bot-deploy
```

## 2. Give GitHub Actions a restricted SSH key

On your own computer, outside the repository, generate a dedicated key:

```bash
ssh-keygen -t ed25519 -N '' -C github-actions-telegram-tts-bot -f ~/.ssh/telegram-tts-bot-actions
```

On the server, use `sudoedit /home/tts-deploy/.ssh/authorized_keys` to insert **one
line**, replacing the example public key with the contents of the new `.pub` file:

```text
restrict,command="sudo -n /usr/local/sbin/deploy-telegram-tts-bot \"$SSH_ORIGINAL_COMMAND\"" ssh-ed25519 REPLACE_WITH_PUBLIC_KEY github-actions-telegram-tts-bot
```

```bash
sudo chown root:root /home/tts-deploy/.ssh/authorized_keys
sudo chmod 644 /home/tts-deploy/.ssh/authorized_keys
```

This key cannot open an interactive shell, upload files, or forward ports. The forced
command accepts only `deploy sha256:<digest>` for `ghcr.io/ihoru/telegram-tts-bot`.
It can deploy any digest in that image repository; protect main and registry write
access accordingly. [OpenSSH authorized-key options](https://man.openbsd.org/sshd.8#AUTHORIZED_KEYS_FILE_FORMAT)

Verify SSH without restarting anything, from your own computer:

```bash
ssh -i ~/.ssh/telegram-tts-bot-actions -o IdentitiesOnly=yes tts-deploy@YOUR_SERVER check
```

Expected result: `Expected: deploy sha256:<64 lowercase hex characters>` and a nonzero
exit code. A sudo/password/permission error means setup is incomplete.

The server's SSH port must be reachable from GitHub-hosted runners. If your firewall
only permits your personal IP, arrange runner access before enabling deployment.
The bot itself needs no inbound port.

## 3. Configure GitHub

In the repository's **Settings → Environments**, create `production` and restrict its
deployment branches to `main`. Leave required reviewers unset for automatic deployment.

In **Settings → Secrets and variables → Actions**, add:

| Type | Name | Value |
| --- | --- | --- |
| Repository variable | `DEPLOY_HOST` | Server IPv4 address or DNS name |
| Repository variable | `DEPLOY_USER` | `tts-deploy` |
| Repository variable | `DEPLOY_PORT` | SSH port; optional, defaults to `22` |
| Repository variable | `DEPLOY_ENABLED` | Leave unset until setup is complete; set to `true` to enable |
| Secret | `DEPLOY_SSH_KEY` | Complete dedicated private key, including BEGIN/END lines |
| Secret | `DEPLOY_KNOWN_HOSTS` | Verified server SSH host public key entry |

For `DEPLOY_KNOWN_HOSTS`, read `/etc/ssh/ssh_host_ed25519_key.pub` using your already
trusted administrator connection or provider console. Prefix that public key with
the exact `DEPLOY_HOST` value. For a nonstandard port use `[HOST]:PORT` instead:

```text
YOUR_SERVER ssh-ed25519 SERVER_HOST_PUBLIC_KEY
```

Use the **server host public key**, not your deployment user's public key. Do not
trust an unverified `ssh-keyscan` result. The workflow enforces strict host checking.

Actions publishes using its built-in `GITHUB_TOKEN`; no registry write token needs
to be created. Existing package permissions must allow this repository's Actions to
write to `ghcr.io/ihoru/telegram-tts-bot`.

For server pulls choose one:

- Make the GHCR package public if the bundled image is intended to be public.
- For a private package, use a server-local GitHub PAT (classic) with `read:packages`
  and access to the package. Run `sudo docker login ghcr.io --username YOUR_GITHUB_USER`
  interactively and enter the token at its password prompt. Root runs the deployment,
  so the login must be available to root. Never put this token in deploy.json or Git.

[GitHub container registry access](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)

## 4. Test with the next feature

1. Commit and push these repository changes with deployment disabled.
2. Complete the server/key/GitHub setup and the harmless `check` command above.
3. Set repository variable `DEPLOY_ENABLED=true`. Changing the variable alone does
   not launch a deployment.
4. Merge or push the next feature to `main` and follow **Actions → CI**. Lint, tests,
   container verification, image publication, and production deployment must succeed.
   PR and tag runs never deploy. Superseded main commits are skipped before SSH.
5. On the server verify the running image's revision against that feature's commit:

```bash
sudo docker inspect --format '{{.Config.Image}}' telegram-tts-bot
sudo docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$(sudo docker inspect --format '{{.Image}}' telegram-tts-bot)"
```

Send a private message to the bot and confirm an OGG voice reply and the new feature.
The automatic check observes startup and ten seconds without restart; it does not
prove Telegram delivery or detect every polling conflict. Ensure other servers or
local processes are not polling the same token.

Build and pull can take time for the large image. The old bot remains running during
the pull. Replacement waits up to ten minutes for active work to finish, then up to
ten minutes for startup. Queued requests are not persisted.

## Rollback and recovery

A failed replacement attempts to restart the original container with its original
configuration, and CI reports failure. A successful deployment leaves a stopped
`telegram-tts-bot-previous` container. Keep its image until the next successful update.
No image or volume pruning is automated.

For manual rollback, first set `DEPLOY_ENABLED=false` and ensure no deployment job is
still running. Then, on the server:

```bash
sudo docker container inspect telegram-tts-bot-previous >/dev/null
sudo docker stop --timeout 600 telegram-tts-bot
sudo docker rm telegram-tts-bot
sudo docker rename telegram-tts-bot-previous telegram-tts-bot
sudo docker start telegram-tts-bot
```

If the host crashed after renaming the old container and no current container exists,
run just the rename and start commands. If startup failed without any previous
container, correct configuration and rerun the failed CI job, or deploy manually.
After an SSH interruption, inspect server state before retrying: the script ignores
hangup and may still be completing deployment. A server lock rejects concurrent runs.
Check operational logs locally; automation does not copy bot logs into Actions.
