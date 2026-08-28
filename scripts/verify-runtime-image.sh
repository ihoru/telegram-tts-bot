#!/bin/sh
set -eu

if [ "$#" -ne 1 ]; then
  echo "usage: $0 IMAGE" >&2
  exit 2
fi

image=$1
artifact_dir=$(mktemp -d)
chmod 755 "$artifact_dir"
container_id=
smoke_token=123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi

cleanup() {
  if [ -n "$container_id" ]; then
    docker rm -f "$container_id" >/dev/null 2>&1 || true
  fi
  rm -rf "$artifact_dir"
}
trap cleanup EXIT HUP INT TERM

test "$(docker image inspect --format \
  '{{ index .Config.Labels "org.opencontainers.image.licenses" }}' "$image")" = \
  "GPL-3.0-or-later AND CC-BY-NC-SA-4.0"
test "$(docker run --rm --entrypoint id "$image" -u)" = "10001"
docker run --rm --entrypoint python "$image" -c \
  "from telegram_tts_bot.speech import create_voice_renderer; import telegram_tts_bot.__main__"
test "$(docker run --rm --entrypoint sha256sum "$image" \
  /opt/silero/v5_5_ru.pt | cut -d ' ' -f 1)" = \
  "50081637b602126ee06cb3bc8a744d25651d2da149ee8864b9a379bfdd934437"
docker run --rm --entrypoint python "$image" -c \
  "import importlib.util, os, torch; assert os.environ['SILERO_MODEL_PATH'] == '/opt/silero/v5_5_ru.pt'; assert os.environ['TTS_VOICE'] == 'kseniya'; assert os.environ['TTS_MAX_CONCURRENCY'] == '2'; assert 'PIPER_MODEL_PATH' not in os.environ; assert 'PIPER_CONFIG_PATH' not in os.environ; assert importlib.util.find_spec('piper') is None; assert torch.__version__ == '2.13.0+cpu'; assert torch.version.cuda is None"
docker run --rm --entrypoint sh "$image" -c "test ! -e /opt/piper"
docker run --rm --entrypoint test "$image" \
  -f /usr/share/doc/vslukh/THIRD_PARTY_NOTICES.md
test "$(docker run --rm --entrypoint sha256sum "$image" \
  /usr/share/doc/vslukh/silero-models-CC-BY-NC-SA-4.0.txt | cut -d ' ' -f 1)" = \
  "1349a4b6148492b44f629e64eed676612e234fe9a839e4f3b277c1482c8849f1"

set +e
timeout 60s docker run --rm --network none \
  --env "TELEGRAM_BOT_TOKEN=$smoke_token" \
  "$image" >"$artifact_dir/stdout" 2>"$artifact_dir/stderr"
status=$?
set -e

cat "$artifact_dir/stderr"
test "$status" = "1"
grep -Fq "bot_stopped exception_type=" "$artifact_dir/stderr"
if grep -Fq "$smoke_token" "$artifact_dir/stderr"; then
  echo "Bot token leaked into startup diagnostics." >&2
  exit 1
fi

container_id=$(docker create --interactive --entrypoint tts-to-ogg "$image" /tmp/voice.ogg)
printf '%s' 'Проверка контейнера' | docker start --attach --interactive "$container_id"
docker cp "$container_id:/tmp/voice.ogg" "$artifact_dir/voice.ogg"
chmod 644 "$artifact_dir/voice.ogg"
docker rm "$container_id" >/dev/null
container_id=

probe=$(docker run --rm \
  --mount "type=bind,source=$artifact_dir,target=/artifacts,readonly" \
  --entrypoint ffprobe "$image" \
  -v error -select_streams a:0 \
  -show_entries stream=codec_name,channels,sample_rate \
  -of default=noprint_wrappers=1 /artifacts/voice.ogg)
printf '%s\n' "$probe"
printf '%s\n' "$probe" | grep -Fqx "codec_name=opus"
printf '%s\n' "$probe" | grep -Fqx "sample_rate=48000"
printf '%s\n' "$probe" | grep -Fqx "channels=1"
