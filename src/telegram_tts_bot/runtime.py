"""Composition root and lifecycle for the long-polling Telegram bot."""

from __future__ import annotations

import asyncio
import logging
import sys
from collections.abc import Awaitable, Callable

from aiogram import Bot, Dispatcher

from telegram_tts_bot.activity import (
    HandlerActivity,
    HandlerActivityMiddleware,
    HandlerLoggingMiddleware,
    UpdateLoggingMiddleware,
)
from telegram_tts_bot.bot_service import BotSpeechService
from telegram_tts_bot.config import BotSettings, ConfigurationError, model_name_for_voice
from telegram_tts_bot.environment import load_repository_environment
from telegram_tts_bot.handlers import VoicePresentation, create_router
from telegram_tts_bot.progress import TelegramProgressCoordinator
from telegram_tts_bot.speech import VoiceRenderer, create_voice_renderer

logger = logging.getLogger(__name__)


def configure_logging(level: int) -> None:
    """Configure concise logs while suppressing third-party update identity logs."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stderr,
    )
    logging.getLogger("aiogram.dispatcher").setLevel(logging.WARNING)
    logging.getLogger("aiogram.event").setLevel(logging.CRITICAL)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)


def create_dispatcher(
    speech_service: BotSpeechService,
    activity: HandlerActivity,
    progress: TelegramProgressCoordinator,
    voice_presentation: VoicePresentation,
) -> Dispatcher:
    """Assemble the aiogram dispatcher and its workflow-data dependencies."""
    dispatcher = Dispatcher(
        speech_service=speech_service,
        progress=progress,
        voice_presentation=voice_presentation,
    )
    dispatcher.update.outer_middleware(UpdateLoggingMiddleware())
    dispatcher.update.outer_middleware(HandlerActivityMiddleware(activity))
    router = create_router()
    router.message.middleware(HandlerLoggingMiddleware())
    dispatcher.include_router(router)
    return dispatcher


async def _close_runtime_resources(
    *,
    activity: HandlerActivity,
    progress: TelegramProgressCoordinator,
    speech_service: BotSpeechService | None,
    renderer: VoiceRenderer | None,
    bot: Bot,
) -> BaseException | None:
    """Cancel queued work, drain active handlers, then close local and remote resources."""
    first_error: BaseException | None = None

    async def run_stage(stage: str, operation: Awaitable[None]) -> None:
        nonlocal first_error
        try:
            await operation
        except BaseException as error:
            logger.error(
                "bot_cleanup_failed cleanup_stage=%s exception_type=%s",
                stage,
                type(error).__name__,
            )
            if first_error is None:
                first_error = error

    await run_stage("handler_stop_accepting", activity.stop_accepting())
    if speech_service is not None:
        await run_stage("speech_queue_shutdown", speech_service.begin_shutdown())
    await run_stage("handler_wait_idle", activity.wait_until_idle())
    await run_stage("telegram_progress", progress.close())
    if speech_service is not None:
        await run_stage("speech_service", speech_service.close())
    elif renderer is not None:
        await run_stage("renderer", renderer.close())
    await run_stage("telegram_session", bot.session.close())
    return first_error


async def run_bot(
    settings: BotSettings,
    *,
    renderer_factory: Callable[..., VoiceRenderer] = create_voice_renderer,
    bot_factory: Callable[[str], Bot] = Bot,
) -> None:
    """Run polling and close handlers, workers, and the Telegram session in order."""
    bot = bot_factory(settings.telegram_bot_token)
    renderer: VoiceRenderer | None = None
    speech_service: BotSpeechService | None = None
    activity = HandlerActivity()
    progress = TelegramProgressCoordinator()
    primary_error: BaseException | None = None
    try:
        renderer = renderer_factory(
            qwen_model_path=settings.qwen_model_path,
            silero_model_path=settings.silero_model_path,
            voice=settings.tts_voice,
            max_workers=settings.max_concurrency,
        )
        speech_service = BotSpeechService(
            renderer,
            global_limit=settings.max_concurrency,
            per_user_limit=settings.max_concurrency_per_user,
            queue_limit=settings.max_queue_size,
            per_user_queue_limit=settings.max_queue_size_per_user,
            queue_wait_seconds=settings.max_queue_wait_seconds,
        )
        dispatcher = create_dispatcher(
            speech_service,
            activity,
            progress,
            VoicePresentation(
                model_name=model_name_for_voice(settings.tts_voice),
                voice_name=settings.tts_voice,
            ),
        )
        await bot.delete_webhook(drop_pending_updates=False)
        logger.info("bot_polling_started")
        await dispatcher.start_polling(bot, close_bot_session=False)
    except BaseException as error:
        primary_error = error
        raise
    finally:
        cleanup_error = await _close_runtime_resources(
            activity=activity,
            progress=progress,
            speech_service=speech_service,
            renderer=renderer,
            bot=bot,
        )
        logger.info("bot_shutdown_complete")
        if cleanup_error is not None and primary_error is None:
            raise cleanup_error


def main() -> None:
    """Load configuration and run the application without exposing secret values."""
    load_repository_environment()
    try:
        settings = BotSettings.from_environment()
    except ConfigurationError as error:
        print(f"configuration error: {error}", file=sys.stderr)
        raise SystemExit(2) from None

    configure_logging(settings.log_level)
    try:
        asyncio.run(run_bot(settings))
    except KeyboardInterrupt:
        return
    except Exception as error:
        logger.critical("bot_stopped exception_type=%s", type(error).__name__)
        raise SystemExit(1) from None
