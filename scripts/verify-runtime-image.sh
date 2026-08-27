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

test "$(docker run --rm --entrypoint id "$image" -u)" = "10001"
docker run --rm --entrypoint python "$image" -c \
  "from telegram_tts_bot.speech import create_voice_renderer; import telegram_tts_bot.__main__"
test "$(docker run --rm --entrypoint sha256sum "$image" \
  /opt/piper/ru_RU-denis-medium.onnx | cut -d ' ' -f 1)" = \
  "15fab56e11a097858ee115545d0f697fc2a316c41a291a5362349fb870411b0a"
test "$(docker run --rm --entrypoint sha256sum "$image" \
  /opt/piper/ru_RU-denis-medium.onnx.json | cut -d ' ' -f 1)" = \
  "831c860dac0b5073eaa81610a0a638ec23d90a6cf8e5f871b4485c2cec3767c8"
docker run --rm --entrypoint test "$image" \
  -f /usr/share/doc/vslukh/piper-voice/MODEL_CARD
docker run --rm --entrypoint test "$image" \
  -f /usr/share/doc/vslukh/THIRD_PARTY_NOTICES.md
docker run --rm --entrypoint test "$image" \
  -f /usr/share/doc/vslukh/piper-voices-MIT.txt

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
