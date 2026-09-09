import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import WebSocketDisconnect

from app.features.chat_overlay import router
from app.features.chat_overlay.broadcaster import ChatOverlayBroadcaster
from app.features.chat_overlay.schemas import ChatOverlayStyleOptions, TimerOverlayStyleOptions
from app.features.chat_overlay.service import ChatOverlayService
from app.features.chat_overlay.timer import OverlayTimerManager, TimerState


class FakeSocket:
    def __init__(self):
        self.messages = []

    async def accept(self):
        pass

    async def send_json(self, payload):
        self.messages.append(payload)

    async def receive_text(self):
        raise WebSocketDisconnect()


def test_timer_connect_sends_state_only_to_new_socket(monkeypatch):
    broadcaster = ChatOverlayBroadcaster()
    manager = OverlayTimerManager()
    manager._states["channel"] = TimerState("timer", 120000, 0, False)
    monkeypatch.setattr(router, "timer_overlay_broadcaster", broadcaster)
    monkeypatch.setattr(router, "overlay_timer_manager", manager)
    existing, new = FakeSocket(), FakeSocket()

    async def run():
        await broadcaster.connect("channel", existing)
        await router.connect_timer_overlay_websocket(new, "channel", TimerOverlayStyleOptions(), "css")

    asyncio.run(run())
    assert existing.messages == []
    assert new.messages[0]["type"] == "overlay-settings"
    assert new.messages[1]["action"] == "sync"
    assert new.messages[1]["timer"]["remaining_ms"] == 0
    assert new not in broadcaster._connections["channel"]


def test_reconnect_clears_timer_deleted_while_offline(monkeypatch):
    monkeypatch.setattr(router, "timer_overlay_broadcaster", ChatOverlayBroadcaster())
    monkeypatch.setattr(router, "overlay_timer_manager", OverlayTimerManager())
    socket = FakeSocket()
    asyncio.run(router.connect_timer_overlay_websocket(socket, "channel", TimerOverlayStyleOptions(), "css"))
    assert socket.messages[-1] == {"type": "timer", "action": "delete", "timer": None}


def test_failed_initial_sync_unregisters_socket(monkeypatch):
    broadcaster = ChatOverlayBroadcaster()
    monkeypatch.setattr(router, "timer_overlay_broadcaster", broadcaster)
    socket = FakeSocket()
    socket.send_json = AsyncMock(side_effect=RuntimeError("closed"))
    with pytest.raises(RuntimeError):
        asyncio.run(router.connect_timer_overlay_websocket(socket, "channel", TimerOverlayStyleOptions(), "css"))
    assert not broadcaster.has_connections("channel")


def test_settings_update_filters_without_changing_preset_connections():
    broadcaster = ChatOverlayBroadcaster()
    default, preset, other = FakeSocket(), FakeSocket(), FakeSocket()

    async def run():
        await broadcaster.connect("channel", default)
        await broadcaster.connect("channel", preset, preset_name="preset")
        await broadcaster.connect("other", other)
        await broadcaster.publish_settings("channel", "css", {"blocked_nicknames": [" blocked "]})
        await broadcaster.publish("channel", {"nickname": "BLOCKED", "message": "hidden"})
        assert len(default.messages) == 1
        assert len(preset.messages) == 1
        assert other.messages == []
        await broadcaster.publish_settings("channel", "preset css", {}, preset_name="preset")
        assert preset.messages[-1]["custom_css"] == "preset css"
        assert len(default.messages) == 1
        await broadcaster.publish_settings("channel", "css", {})
        await broadcaster.publish("channel", {"nickname": "BLOCKED", "message": "visible"})
        assert default.messages[-1]["message"] == "visible"

    asyncio.run(run())


def test_replay_has_new_identity_and_no_absolute_time_fields(monkeypatch):
    from app.features.chat_overlay import timer

    manager = OverlayTimerManager()
    manager.publish_snapshot = AsyncMock()
    monkeypatch.setattr(timer, "_now_ms", lambda: 1000000)

    async def run():
        await manager.set_timer("channel", "timer", 120, False)
        initial = manager.get_snapshot("channel")
        assert initial["remaining_ms"] == 120000
        assert not initial["running"]
        await manager.play("channel")
        assert manager.get_snapshot("channel")["timer_id"] == initial["timer_id"]
        manager._states["channel"].ends_at_ms = 1
        await manager.play("channel")
        replay = manager.get_snapshot("channel")
        assert replay["timer_id"] != initial["timer_id"]
        assert replay["remaining_ms"] == 120000
        assert "ends_at_ms" not in replay
        assert "started_at_ms" not in replay

    asyncio.run(run())


def test_missing_or_deleted_preset_follows_defaults_until_recreated():
    broadcaster = ChatOverlayBroadcaster()
    socket = FakeSocket()

    async def run():
        await broadcaster.connect("channel", socket, preset_name="preset", uses_default_settings=True)
        await broadcaster.publish_settings("channel", "default css", {})
        assert socket.messages[-1]["custom_css"] == "default css"
        await broadcaster.publish_settings("channel", "preset css", {}, preset_name="preset")
        await broadcaster.publish_settings("channel", "new default css", {})
        assert socket.messages[-1]["custom_css"] == "preset css"
        await broadcaster.publish_settings("channel", "fallback css", {}, preset_name="preset", uses_default_settings=True)
        await broadcaster.publish_settings("channel", "latest default css", {})
        assert socket.messages[-1]["custom_css"] == "latest default css"

    asyncio.run(run())


@pytest.mark.parametrize("kind,options", [("chat", ChatOverlayStyleOptions()), ("timer", TimerOverlayStyleOptions())])
def test_save_publishes_committed_settings(kind, options):
    db = SimpleNamespace(commit=AsyncMock(), refresh=AsyncMock())
    service = ChatOverlayService(db)
    channel = SimpleNamespace(platform_channel_id="channel")
    setting = SimpleNamespace(overlay_kind=kind)
    service.get_or_create_setting = AsyncMock(return_value=(channel, setting))

    async def check_publish(*args):
        db.commit.assert_awaited_once()
        assert setting.style_options == options.model_dump()

    service._publish_settings = AsyncMock(side_effect=check_publish)
    asyncio.run(service.update_setting("chzzk", "channel", kind, "", True, style_options=options))
    service._publish_settings.assert_awaited_once_with(channel, setting)
