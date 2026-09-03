#!/bin/sh
set -eu

repository_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
source_file="$repository_root/assets/read-aloud-avatar.svg"
output_file="$repository_root/assets/read-aloud-avatar.png"
temporary_file="$repository_root/assets/.read-aloud-avatar.png.tmp"

if ! command -v convert >/dev/null 2>&1; then
  echo "ImageMagick 'convert' is required to render the avatar." >&2
  exit 1
fi

trap 'rm -f "$temporary_file"' EXIT HUP INT TERM

convert \
  -background none \
  "$source_file" \
  -resize '1024x1024!' \
  -strip \
  -define png:compression-level=9 \
  -define png:exclude-chunks=date,time \
  "PNG24:$temporary_file"

mv "$temporary_file" "$output_file"
trap - EXIT HUP INT TERM
