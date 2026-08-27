# syntax=docker/dockerfile:1.7@sha256:a57df69d0ea827fb7266491f2813635de6f17269be881f696fbfdf2d83dda33e

# This project deliberately publishes linux/amd64 only. Both source images resolve to
# amd64 manifests, not mutable multi-platform indexes.
FROM ghcr.io/astral-sh/uv:0.11.28@sha256:5c3ab83183a73c5d319a77009eb425b60d5bb937f339fb7876788ebf567baf48 AS uv

FROM scratch AS voice
ADD --checksum=sha256:15fab56e11a097858ee115545d0f697fc2a316c41a291a5362349fb870411b0a \
    https://huggingface.co/rhasspy/piper-voices/resolve/39ab474be869e9181350af6a65e4953eef67aaa0/ru/ru_RU/denis/medium/ru_RU-denis-medium.onnx \
    /voice/ru_RU-denis-medium.onnx
ADD --checksum=sha256:831c860dac0b5073eaa81610a0a638ec23d90a6cf8e5f871b4485c2cec3767c8 \
    https://huggingface.co/rhasspy/piper-voices/resolve/39ab474be869e9181350af6a65e4953eef67aaa0/ru/ru_RU/denis/medium/ru_RU-denis-medium.onnx.json \
    /voice/ru_RU-denis-medium.onnx.json
ADD --checksum=sha256:8b5d685dd80f8ad3f8dbbe1c56b16bb0809f00c144af3642dbcf3b707eb89c12 \
    https://huggingface.co/rhasspy/piper-voices/raw/39ab474be869e9181350af6a65e4953eef67aaa0/ru/ru_RU/denis/medium/MODEL_CARD \
    /voice/MODEL_CARD

FROM python:3.14.6-slim-bookworm@sha256:ff83a535339812dd72e69c93b3c48ddf7c85a324d6330af5797c82a255dbeef4 AS build

ENV SOURCE_DATE_EPOCH=0 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app
COPY --from=uv /uv /uvx /usr/local/bin/
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

FROM build AS test

COPY docker/debian.sources /etc/apt/sources.list.d/debian.sources
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install --yes --no-install-recommends \
        ca-certificates ffmpeg time \
    && rm -rf /var/lib/apt/lists/*
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --all-groups --no-editable
COPY --from=voice /voice /opt/piper
COPY tests ./tests
ENV PIPER_MODEL_PATH=/opt/piper/ru_RU-denis-medium.onnx \
    PIPER_CONFIG_PATH=/opt/piper/ru_RU-denis-medium.onnx.json
CMD ["uv", "run", "--locked", "pytest"]

FROM python:3.14.6-slim-bookworm@sha256:ff83a535339812dd72e69c93b3c48ddf7c85a324d6330af5797c82a255dbeef4 AS runtime

ARG APP_UID=10001
ARG APP_VERSION=0.1.0
ARG VCS_REF=unknown

LABEL org.opencontainers.image.title="Vslukh" \
      org.opencontainers.image.description="Local-first Telegram text-to-speech bot" \
      org.opencontainers.image.licenses="GPL-3.0-or-later" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.revision="${VCS_REF}"

COPY docker/debian.sources /etc/apt/sources.list.d/debian.sources
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install --yes --no-install-recommends \
        ca-certificates ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid "${APP_UID}" vslukh \
    && useradd --uid "${APP_UID}" --gid "${APP_UID}" --no-create-home \
        --home-dir /nonexistent --shell /usr/sbin/nologin vslukh

WORKDIR /app
COPY --from=build --chown=${APP_UID}:${APP_UID} /app/.venv /app/.venv
COPY --from=voice --chown=${APP_UID}:${APP_UID} \
    /voice/ru_RU-denis-medium.onnx \
    /voice/ru_RU-denis-medium.onnx.json \
    /opt/piper/
COPY --from=voice /voice/MODEL_CARD /usr/share/doc/vslukh/piper-voice/MODEL_CARD
COPY LICENSE THIRD_PARTY_NOTICES.md licenses/piper-voices-MIT.txt /usr/share/doc/vslukh/

ENV HOME=/nonexistent \
    PATH=/app/.venv/bin:$PATH \
    PIPER_MODEL_PATH=/opt/piper/ru_RU-denis-medium.onnx \
    PIPER_CONFIG_PATH=/opt/piper/ru_RU-denis-medium.onnx.json \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

USER ${APP_UID}:${APP_UID}
STOPSIGNAL SIGTERM
ENTRYPOINT ["python", "-m", "telegram_tts_bot"]
