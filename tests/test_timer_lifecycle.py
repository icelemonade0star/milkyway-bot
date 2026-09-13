import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.features.chat.handling import cmd_timer
from app.features.chat_overlay import timer
from app.features.chat_overlay.schemas import TimerOverlayStyleOptions


@pytest.mark.parametrize("text,expected", [
    ("2:00", 120), ("01:02:03", 3723), ("2", 120), ("120s", 120),
    ("24h", 86400), ("24:00:01", None), ("00:00", None), ("1:60", None),
    ("-2", None), ("text", None), ("1h30m", 5400),
])
def test_duration_parsing(text, expected):
    assert timer.parse_timer_duration(text) == expected


def test_pause_resume_replay_delete_and_channel_isolation(monkeypatch):
    now = 1000000
    monkeypatch.setattr(timer, "_now_ms", lambda: now)
    manager = timer.OverlayTimerManager()
    manager.publish_snapshot = AsyncMock()
    monkeypatch.setattr(timer.timer_overlay_broadcaster, "publish", AsyncMock())

    async def run():
        nonlocal now
        await manager.set_timer("one", "first", 120, True)
        await manager.set_timer("two", "second", 60, False)
        now += 20000
        assert manager.get_snapshot("one")["remaining_ms"] == 100000
        assert await manager.pause("one")
        now += 30000
        assert manager.get_snapshot("one")["remaining_ms"] == 100000
        assert await manager.play("one")
        now += 100000
        assert manager.get_snapshot("one")["remaining_ms"] == 0
        assert not manager.get_snapshot("one")["running"]
        assert await manager.play("one")
        assert manager.get_snapshot("one")["remaining_ms"] == 120000
        assert await manager.clear("one")
        assert manager.get_snapshot("one") is None
        assert not await manager.play("one")
        assert not await manager.pause("one")
        assert manager.get_snapshot("two")["remaining_ms"] == 60000
        assert not manager.get_snapshot("two")["running"]

    asyncio.run(run())


@pytest.mark.parametrize("autoplay", [True, False])
@pytest.mark.parametrize("args,title", [(["2:00"], "Default"), (["Penalty", "2:00"], "Penalty"), (["Daily", "Penalty", "2:00"], "Daily Penalty")])
def test_create_command_title_and_autoplay(monkeypatch, autoplay, args, title):
    options = TimerOverlayStyleOptions(timer_autoplay=autoplay, timer_title_text="Default")
    monkeypatch.setattr(cmd_timer, "_get_timer_options", AsyncMock(return_value=options))
    manager = SimpleNamespace(set_timer=AsyncMock())
    monkeypatch.setattr(cmd_timer, "overlay_timer_manager", manager)
    session = SimpleNamespace(send_chat=AsyncMock())
    asyncio.run(cmd_timer.handle_timer_command(session, object(), "channel", args))
    manager.set_timer.assert_awaited_once_with("channel", title, 120, autoplay)
