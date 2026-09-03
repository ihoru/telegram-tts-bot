import asyncio
from dataclasses import dataclass, field
from typing import Any, cast

from aiogram import Bot
from aiogram.enums import ChatAction
from aiogram.exceptions import TelegramRetryAfter
from aiogram.methods import SendChatAction
from aiogram.types import ReplyParameters

from telegram_tts_bot.progress import ReplyTarget, TelegramProgressCoordinator


class ManualSleep:
    def __init__(self) -> None:
        self.calls: asyncio.Queue[tuple[float, asyncio.Event]] = asyncio.Queue()

    async def __call__(self, delay: float) -> None:
        release = asyncio.Event()
        self.calls.put_nowait((delay, release))
        await release.wait()


@dataclass(eq=False)
class FakeBot:
    chat_actions: list[tuple[int, str]] = field(default_factory=list)
    messages: list[tuple[int, str, ReplyParameters | None]] = field(default_factory=list)
    action_failures: list[Exception] = field(default_factory=list)

    async def send_chat_action(self, *, chat_id: int, action: str) -> bool:
        if self.action_failures:
            raise self.action_failures.pop(0)
        self.chat_actions.append((chat_id, action))
        return True

    async def send_message(
        self,
        *,
        chat_id: int,
        text: str,
        reply_parameters: ReplyParameters | None = None,
    ) -> None:
        self.messages.append((chat_id, text, reply_parameters))


def as_bot(bot: FakeBot) -> Bot:
    return cast(Bot, cast(Any, bot))


def target(bot: FakeBot) -> ReplyTarget:
    return ReplyTarget(bot=as_bot(bot), chat_id=42, message_id=9)


async def test_backlog_sends_one_notice_and_resets_after_empty() -> None:
    bot = FakeBot()
    sleep = ManualSleep()
    progress = TelegramProgressCoordinator(sleep=sleep)
    reply_target = target(bot)

    await progress.enter_backlog(
        user_id=7,
        backlog_id=1,
        target=reply_target,
        text="wait",
    )
    await progress.enter_backlog(
        user_id=7,
        backlog_id=1,
        target=reply_target,
        text="ignored duplicate",
    )
    delay, release = await sleep.calls.get()
    assert delay == 5
    assert sleep.calls.empty()

    release.set()
    await asyncio.sleep(0)
    assert [(chat_id, text) for chat_id, text, _ in bot.messages] == [(42, "wait")]

    await progress.leave_backlog(user_id=7, backlog_id=1)
    await progress.leave_backlog(user_id=7, backlog_id=1)
    await progress.enter_backlog(
        user_id=7,
        backlog_id=2,
        target=reply_target,
        text="new backlog",
    )
    second_delay, second_release = await sleep.calls.get()
    assert second_delay == 5
    second_release.set()
    await asyncio.sleep(0)
    assert [text for _, text, _ in bot.messages] == ["wait", "new backlog"]
    await progress.leave_backlog(user_id=7, backlog_id=2)
    await progress.close()


async def test_backlog_that_starts_before_delay_sends_nothing() -> None:
    bot = FakeBot()
    sleep = ManualSleep()
    progress = TelegramProgressCoordinator(sleep=sleep)
    await progress.enter_backlog(user_id=1, backlog_id=1, target=target(bot), text="wait")
    _, release = await sleep.calls.get()

    await progress.leave_backlog(user_id=1, backlog_id=1)
    release.set()
    await asyncio.sleep(0)

    assert bot.messages == []
    await progress.close()


async def test_identical_responses_are_coalesced_for_five_seconds() -> None:
    bot = FakeBot()
    sleep = ManualSleep()
    progress = TelegramProgressCoordinator(sleep=sleep)
    reply_target = target(bot)

    await progress.send_coalesced(
        user_id=1,
        kind="full",
        target=reply_target,
        text="first",
    )
    await progress.send_coalesced(
        user_id=1,
        kind="full",
        target=reply_target,
        text="duplicate",
    )
    delay, release = await sleep.calls.get()
    assert delay == 5
    assert [text for _, text, _ in bot.messages] == ["first"]

    release.set()
    await asyncio.sleep(0)
    await progress.send_coalesced(
        user_id=1,
        kind="full",
        target=reply_target,
        text="after cooldown",
    )
    assert [text for _, text, _ in bot.messages] == ["first", "after cooldown"]
    await progress.close()


async def test_active_renders_share_one_chat_action_loop() -> None:
    bot = FakeBot()
    sleep = ManualSleep()
    progress = TelegramProgressCoordinator(sleep=sleep)
    reply_target = target(bot)
    first = progress.rendering(reply_target)
    second = progress.rendering(reply_target)

    await first.__aenter__()
    await second.__aenter__()
    await asyncio.sleep(0)
    assert bot.chat_actions == [(42, ChatAction.RECORD_VOICE)]
    delay, release = await sleep.calls.get()
    assert delay == 4
    release.set()
    for _ in range(10):
        if len(bot.chat_actions) == 2:
            break
        await asyncio.sleep(0)
    assert bot.chat_actions == [
        (42, ChatAction.RECORD_VOICE),
        (42, ChatAction.RECORD_VOICE),
    ]

    await first.__aexit__(None, None, None)
    await second.__aexit__(None, None, None)
    await progress.close()


async def test_activity_honors_retry_after_and_backs_off_other_failures() -> None:
    method = SendChatAction(chat_id=42, action=ChatAction.RECORD_VOICE)
    bot = FakeBot(
        action_failures=[
            TelegramRetryAfter(method=method, message="rate limited", retry_after=7),
            RuntimeError("network"),
            RuntimeError("network again"),
        ]
    )
    sleep = ManualSleep()
    progress = TelegramProgressCoordinator(sleep=sleep)
    context = progress.rendering(target(bot))
    await context.__aenter__()
    await asyncio.sleep(0)

    retry_delay, release_retry = await sleep.calls.get()
    assert retry_delay == 7
    release_retry.set()
    await asyncio.sleep(0)
    failure_delay, release_failure = await sleep.calls.get()
    assert failure_delay == 4
    release_failure.set()
    await asyncio.sleep(0)
    second_failure_delay, _ = await sleep.calls.get()
    assert second_failure_delay == 8

    await context.__aexit__(None, None, None)
    await progress.close()


async def test_unbound_targets_skip_telegram_calls() -> None:
    progress = TelegramProgressCoordinator()
    unbound = ReplyTarget(bot=None, chat_id=1, message_id=2)
    await progress.send_coalesced(user_id=1, kind="notice", target=unbound, text="text")
    async with progress.rendering(unbound):
        pass
    await progress.close()
