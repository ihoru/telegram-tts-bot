# Server deployment

Read Aloud runs as one long-lived Docker container that polls Telegram. It does not expose
an HTTP service, so it needs outbound internet access but no domain, reverse proxy, or
inbound port.

This guide assumes a Linux amd64 server with Git and
[Docker Engine](https://docs.docker.com/engine/install/). Deploy an immutable release
tag or commit rather than a moving branch. Exactly one running process may poll a
BotFather token at a time.

## Choose a voice runtime

- Qwen Aiden or Serena is the default and supports mixed Russian-English text. It
  requires one NVIDIA CUDA/BF16 GPU with 8 GiB VRAM, at least 8 GiB host RAM, and the
  NVIDIA Container Toolkit. Keep `TTS_MAX_CONCURRENCY=1`.
- Silero kseniya, xenia, or baya runs on CPU. The measured two-render baseline is two
  CPUs and 1 GiB RAM. The bundled Silero model is CC BY-NC-SA 4.0 and limited to
  NonCommercial use unless separate permission has been obtained.

## Check out and configure Read Aloud

Create a dedicated application directory and clone the repository:

```bash
sudo mkdir -p /opt/telegram-tts-bot
sudo chown "$(id -u):$(id -g)" /opt/telegram-tts-bot
git clone ssh://git@github.com/ihoru/telegram-tts-bot.git /opt/telegram-tts-bot
cd /opt/telegram-tts-bot
git checkout --detach origin/main
```

This checks out the exact `origin/main` commit fetched by the clone rather than leaving
the server on a moving local branch. Substitute an approved release tag or full commit
when deploying a different revision.

Copy the environment template, restrict it to the current account, and edit it:

```bash
cp .env.example .env
chmod 600 .env
editor .env
```

Set the BotFather token:

```dotenv
TELEGRAM_BOT_TOKEN=replace-with-real-botfather-token
```

Never put the token in the image, repository, build arguments, command line, CI
configuration, or logs.

For CPU-only Silero, also set a Silero voice and the validated concurrency:

```dotenv
TTS_VOICE=kseniya
TTS_MAX_CONCURRENCY=2
```

For Qwen, keep the default `TTS_VOICE=aiden`, or select `serena`, and keep
`TTS_MAX_CONCURRENCY=1`.

## Build the image

From `/opt/telegram-tts-bot`, build the production target. Use a tag that identifies the checked
out release or commit:

```bash
docker build --platform linux/amd64 --target runtime -t telegram-tts-bot:release .
```

The final image is approximately 6.22 GB uncompressed. It runs as unprivileged numeric
UID and GID `10001` and contains FFmpeg, SoX, the application, and the Silero model. Qwen
weights are deliberately excluded.

## Run on CPU with Silero

The Silero model is already present in the image, so no model mount or GPU is needed:

```bash
docker run --detach \
  --name telegram-tts-bot \
  --init \
  --restart unless-stopped \
  --stop-timeout 600 \
  --env-file /opt/telegram-tts-bot/.env \
  --log-driver local \
  --log-opt max-size=10m \
  --log-opt max-file=3 \
  telegram-tts-bot:release
```

## Run on an NVIDIA GPU with Qwen

Install the NVIDIA driver and
[NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)
using their instructions for the server distribution. Confirm that Docker can access
the selected GPU before continuing.

The Qwen snapshot is approximately 2.5 GB. Provision the exact pinned files into a host
directory using the application image:

```bash
sudo install -d -o 10001 -g 10001 /opt/telegram-tts-models

docker run --rm --init \
  --entrypoint python \
  --env HF_HUB_OFFLINE=0 \
  --env TRANSFORMERS_OFFLINE=0 \
  --mount type=bind,source=/opt/telegram-tts-models,target=/models \
  telegram-tts-bot:release \
  -m telegram_tts_bot.speech.qwen_model \
  --output-dir /models/qwen3-tts-12hz-0.6b-customvoice
```

The provisioner downloads the pinned revision, verifies every checksum, and atomically
installs the completed directory. It re-verifies and reuses an existing valid directory.
The production container mounts that directory read-only and runs with network model
downloads disabled:

```bash
docker run --detach \
  --name telegram-tts-bot \
  --init \
  --restart unless-stopped \
  --stop-timeout 600 \
  --gpus device=0 \
  --env-file /opt/telegram-tts-bot/.env \
  --mount type=bind,source=/opt/telegram-tts-models/qwen3-tts-12hz-0.6b-customvoice,target=/models/qwen3-tts-12hz-0.6b-customvoice,readonly \
  --log-driver local \
  --log-opt max-size=10m \
  --log-opt max-file=3 \
  telegram-tts-bot:release
```

## Verify the deployment

Inspect the container and recent logs:

```bash
docker ps --filter name=telegram-tts-bot
docker logs --tail 100 telegram-tts-bot
```

A successful start logs `bot_polling_started`. Send the bot an ordinary private text
message and confirm that it returns an OGG/Opus voice note. If Telegram reports a
polling conflict, another process is using the same token; stop it before retrying.

Follow content-free operational logs when diagnosing a live instance:

```bash
docker logs --follow --tail 100 telegram-tts-bot
```

## Stop, restart, and upgrade

Restart the current image without replacing the container:

```bash
docker restart --timeout 600 telegram-tts-bot
```

The extended timeout lets `SIGTERM` finish an active render and upload. Queued work is
cancelled during graceful shutdown; queue state exists only in process memory and is
never recovered after a restart.

To deploy a new release, fetch and check out its immutable tag or commit, build a new
image tag, and then replace the old container. Stop the old container before starting
the new one so two replicas never poll the same token:

```bash
cd /opt/telegram-tts-bot
git fetch --tags origin
git checkout --detach origin/main
docker build --platform linux/amd64 --target runtime -t telegram-tts-bot:new-release .

docker stop --timeout 600 telegram-tts-bot
docker rm telegram-tts-bot
```

Start `telegram-tts-bot:new-release` using the corresponding CPU or GPU command above. The `.env`
file and external Qwen model directory survive container replacement. After verifying
the new instance, retain the previous image until rollback is no longer needed.

To roll back, gracefully remove the current container and repeat the same run command
with the previous immutable image tag. The environment and model mount require no data
migration.
