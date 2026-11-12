# syntax=docker/dockerfile:1.7@sha256:a57df69d0ea827fb7266491f2813635de6f17269be881f696fbfdf2d83dda33e

# This project deliberately publishes linux/amd64 only. Both source images resolve to
# amd64 manifests, not mutable multi-platform indexes.
FROM ghcr.io/astral-sh/uv:0.13.7@sha256:96f40d3904aad8d0bd010539001d36c8e2188b981e1334471a90c4a1d93bb490 AS uv

FROM scratch AS voice
ADD --checksum=sha256:50081637b602126ee06cb3bc8a744d25651d2da149ee8864b9a379bfdd934437 \
    https://models.silero.ai/models/tts/ru/v5_5_ru.pt \
    /voice/v5_5_ru.pt

FROM python:3.15.0-slim-bookworm@sha256:0e019bbdfb5d9874cb2389f1c2884b64aa2ac97c99960b5bc521cef978c0617d AS build-base

ENV SOURCE_DATE_EPOCH=0 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app
COPY --from=uv /uv /uvx /usr/local/bin/
COPY pyproject.toml uv.lock ./

# Cache each complete runtime's dependencies before application source changes.
FROM build-base AS dependencies-gpu
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --extra gpu --no-install-project --no-editable

FROM build-base AS dependencies-cpu
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --extra cpu --no-install-project --no-editable

FROM dependencies-gpu AS build
COPY README.md LICENSE ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --extra gpu --no-editable

FROM dependencies-cpu AS build-cpu
COPY README.md LICENSE ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --extra cpu --no-editable

FROM build-base AS test-base

COPY docker/debian.sources /etc/apt/sources.list.d/debian.sources
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install --yes --no-install-recommends \
        ca-certificates ffmpeg sox time \
    && rm -rf /var/lib/apt/lists/*
COPY README.md LICENSE ./
COPY src ./src
COPY --from=voice /voice /opt/silero
COPY tests ./tests
COPY scripts ./scripts
ENV SILERO_MODEL_PATH=/opt/silero/v5_5_ru.pt \
    TTS_VOICE=kseniya \
    TTS_MAX_CONCURRENCY=2
CMD ["/app/.venv/bin/pytest"]

FROM test-base AS test
COPY --from=build /app/.venv /app/.venv
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --extra gpu --no-editable

FROM test-base AS test-cpu
COPY --from=build-cpu /app/.venv /app/.venv
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --extra cpu --no-editable

FROM python:3.15.0-slim-bookworm@sha256:0e019bbdfb5d9874cb2389f1c2884b64aa2ac97c99960b5bc521cef978c0617d AS runtime-base

ARG APP_UID=10001
ARG APP_VERSION=0.1.0
ARG VCS_REF=unknown

LABEL org.opencontainers.image.title="Read Aloud" \
      org.opencontainers.image.description="Local-first Telegram text-to-speech bot" \
      org.opencontainers.image.licenses="GPL-3.0-or-later AND CC-BY-NC-SA-4.0 AND Apache-2.0 AND MIT" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.revision="${VCS_REF}"

COPY docker/debian.sources /etc/apt/sources.list.d/debian.sources
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install --yes --no-install-recommends \
        ca-certificates ffmpeg sox \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid "${APP_UID}" ttsbot \
    && useradd --uid "${APP_UID}" --gid "${APP_UID}" --no-create-home \
        --home-dir /nonexistent --shell /usr/sbin/nologin ttsbot

WORKDIR /app
COPY --from=voice --chown=${APP_UID}:${APP_UID} /voice/v5_5_ru.pt /opt/silero/
COPY LICENSE THIRD_PARTY_NOTICES.md licenses/silero-models-CC-BY-NC-SA-4.0.txt \
    licenses/faster-qwen3-tts-MIT.txt \
    licenses/qwen3-tts-Apache-2.0.txt \
    /usr/share/doc/telegram-tts-bot/

ENV HOME=/nonexistent \
    PATH=/app/.venv/bin:$PATH \
    QWEN_MODEL_PATH=/models/qwen3-tts-12hz-0.6b-customvoice \
    SILERO_MODEL_PATH=/opt/silero/v5_5_ru.pt \
    TTS_VOICE=aiden \
    TTS_MAX_CONCURRENCY=1 \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    HF_HUB_DISABLE_TELEMETRY=1 \
    DO_NOT_TRACK=1 \
    ORT_DISABLE_TELEMETRY=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

USER ${APP_UID}:${APP_UID}
STOPSIGNAL SIGTERM
ENTRYPOINT ["python", "-m", "telegram_tts_bot"]

# The CPU target copies a CPU-only environment; it never inherits GPU layers.
FROM runtime-base AS runtime-cpu
LABEL io.iho.tts.runtime="cpu"
COPY --from=build-cpu --chown=${APP_UID}:${APP_UID} /app/.venv /app/.venv
ENV TTS_VOICE=xenia

# Keep the last/default target and historical runtime name compatible with GPU users.
FROM runtime-base AS runtime
LABEL io.iho.tts.runtime="gpu"
COPY --from=build --chown=${APP_UID}:${APP_UID} /app/.venv /app/.venv
