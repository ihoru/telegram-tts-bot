"""Composition root and lifecycle for the long-polling Telegram bot."""

from __future__ import annotations

import asyncio
import logging
import sys
from collections.abc import Awaitable, Callable

from aiogram import Bot, Dispatcher

from telegram_tts_bot.activity import HandlerActivity, HandlerActivityMiddleware
from telegram_tts_bot.bot_service import BotSpeechService
from telegram_tts_bot.config import BotSettings, ConfigurationError
from telegram_tts_bot.handlers import create_router
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
) -> Dispatcher:
    """Assemble the aiogram dispatcher and its workflow-data dependencies."""
    dispatcher = Dispatcher(speech_service=speech_service)
    dispatcher.update.outer_middleware(HandlerActivityMiddleware(activity))
    dispatcher.include_router(create_router())
    return dispatcher


async def _close_runtime_resources(
    *,
    activity: HandlerActivity,
    speech_service: BotSpeechService | None,
    renderer: VoiceRenderer | None,
    bot: Bot,
) -> BaseException | None:
    """Attempt every shutdown stage and return the first failure."""
    operations: list[tuple[str, Awaitable[None]]] = [
        ("handler_activity", activity.stop_and_wait()),
    ]
    if speech_service is not None:
        operations.append(("speech_service", speech_service.close()))
    elif renderer is not None:
        operations.append(("renderer", renderer.close()))
    operations.append(("telegram_session", bot.session.close()))

    first_error: BaseException | None = None
    for stage, operation in operations:
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
        )
        dispatcher = create_dispatcher(speech_service, activity)
        await bot.delete_webhook(drop_pending_updates=False)
        logger.info("bot_polling_started")
        await dispatcher.start_polling(bot, close_bot_session=False)
    except BaseException as error:
        primary_error = error
        raise
    finally:
        cleanup_error = await _close_runtime_resources(
            activity=activity,
            speech_service=speech_service,
            renderer=renderer,
            bot=bot,
        )
        logger.info("bot_shutdown_complete")
        if cleanup_error is not None and primary_error is None:
            raise cleanup_error


def main() -> None:
    """Load configuration and run the application without exposing secret values."""
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
