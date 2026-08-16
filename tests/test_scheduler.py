"""Tests for the generic scheduled-job executor (aangan.scheduler.scheduler._execute).

No real discord.Client/Gemini/DB — a fake client/channel stub exercises the
build-then-post chokepoint and its two failure paths in isolation.
"""

from unittest.mock import AsyncMock, MagicMock

from apscheduler.triggers.cron import CronTrigger

from aangan.insights.answer import ChannelMessage
from aangan.scheduler.scheduler import ScheduledJob, _execute


def _fake_client(channel):
    client = MagicMock()
    client.get_channel.return_value = channel
    return client


async def test_execute_skips_send_when_build_fails():
    async def build():
        raise RuntimeError("build boom")

    job = ScheduledJob(name="test_job", trigger=CronTrigger(), build=build, channel_id=1)
    channel = MagicMock()
    channel.send = AsyncMock()

    await _execute(_fake_client(channel), job)

    channel.send.assert_not_called()


async def test_execute_swallows_send_failure():
    async def build():
        return ChannelMessage(text="hello")

    job = ScheduledJob(name="test_job", trigger=CronTrigger(), build=build, channel_id=1)
    channel = MagicMock()
    channel.send = AsyncMock(side_effect=RuntimeError("send boom"))

    await _execute(_fake_client(channel), job)  # must not raise

    channel.send.assert_called_once()


async def test_execute_posts_with_everyone_mention():
    async def build():
        return ChannelMessage(text="hello household")

    job = ScheduledJob(name="test_job", trigger=CronTrigger(), build=build, channel_id=1)
    channel = MagicMock()
    channel.send = AsyncMock()

    await _execute(_fake_client(channel), job)

    channel.send.assert_called_once()
    args, kwargs = channel.send.call_args
    assert args[0] == "@everyone\nhello household"
    assert kwargs["file"] is None
    assert kwargs["allowed_mentions"].everyone is True
