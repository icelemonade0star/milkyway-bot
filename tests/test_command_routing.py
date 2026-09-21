import asyncio
import os
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock

import pytest

os.environ.setdefault("CLIENT_SECRET", "test-client-secret")

from app.features.chat.handling import handler
from app.features.chat.service import ChatService


def command(name, kind="text", response="response"):
    return NS(command=name, type=kind, response=response, is_active=True, cooldown_seconds=10)


class Cooldown:
    def __init__(self):
        self.keys = set()

    async def check_and_set_cooldown(self, channel, key, seconds, platform):
        if key in self.keys:
            return True
        self.keys.add(key)
        return False


def setup_route(monkeypatch, custom=None, global_command=None):
    service = NS(get_chat_command=AsyncMock(return_value=custom),
                 get_global_commands=AsyncMock(return_value=global_command),
                 process_attendance=AsyncMock(return_value={"status": "checked", "total": 1, "streak": 1}))
    monkeypatch.setattr(handler, "ChatService", lambda db: service)
    return service, NS(send_chat=AsyncMock()), Cooldown()


async def invoke(session, redis, name, role="common_user", user="user"):
    await handler.on_command(None, session, "channel", name, [], role, redis, "!", user, "name")


@pytest.mark.parametrize("role,allowed", [(None, False), ("", False), ("unknown", False),
    ("common_user", False), ("streamer", True), ("channel_manager", True),
    ("manager", True), ("streaming_chat_manager", True)])
@pytest.mark.parametrize("name", ["명령어등록", "타이머", "등록별칭"])
def test_admin_roles_are_explicit(monkeypatch, role, allowed, name):
    service, session, redis = setup_route(monkeypatch, global_command=command("명령어등록|등록별칭", "system"))
    dispatch, timer = AsyncMock(), AsyncMock()
    monkeypatch.setattr(handler, "_dispatch_system_command", dispatch)
    monkeypatch.setattr(handler, "handle_timer_command", timer)
    asyncio.run(invoke(session, redis, name, role))
    target = timer if name == "타이머" else dispatch
    assert target.await_count == int(allowed)
    if allowed and name != "타이머":
        assert dispatch.await_args.args[4] == "명령어등록"


@pytest.mark.parametrize("kind", ["text", "attendance"])
@pytest.mark.parametrize("global_scope", [True, False])
def test_aliases_share_cooldown(monkeypatch, kind, global_scope):
    cmd = command("hello|hi", kind)
    service, session, redis = setup_route(monkeypatch,
        custom=None if global_scope else cmd, global_command=cmd if global_scope else None)

    async def run():
        await invoke(session, redis, "hello")
        await invoke(session, redis, "hi")
        if kind == "attendance":
            await invoke(session, redis, "hi", user="other")
    asyncio.run(run())
    assert session.send_chat.await_count == (2 if kind == "attendance" else 1)


def test_global_redirect_shares_target_cooldown(monkeypatch):
    target = command("hello|hi")
    service, session, redis = setup_route(monkeypatch, global_command=target)
    service.get_chat_command.side_effect = [command("shortcut", "global", "hi"), None]
    async def run():
        await invoke(session, redis, "shortcut")
        await invoke(session, redis, "hello")
    asyncio.run(run())
    session.send_chat.assert_awaited_once()


def test_admin_alias_cannot_be_shadowed_by_custom_command(monkeypatch):
    service, session, redis = setup_route(monkeypatch, custom=command("alias"),
        global_command=command("공지|alias", "system"))
    dispatch = AsyncMock()
    monkeypatch.setattr(handler, "_dispatch_system_command", dispatch)
    asyncio.run(invoke(session, redis, "alias"))
    session.send_chat.assert_not_awaited()
    dispatch.assert_not_awaited()


@pytest.mark.parametrize("name", ["alias|명령어", "명령어|alias"])
def test_public_system_alias_executes_canonical_action(monkeypatch, name):
    service, session, redis = setup_route(monkeypatch, global_command=command(name, "system"))
    dispatch = AsyncMock()
    monkeypatch.setattr(handler, "_dispatch_system_command", dispatch)
    asyncio.run(invoke(session, redis, "alias"))
    assert dispatch.await_args.args[4] == "명령어"


def registration_service(rows=()):
    result = NS(scalars=lambda: NS(all=lambda: list(rows)), scalar_one=lambda: len(rows))
    db = NS(execute=AsyncMock(return_value=result), commit=AsyncMock(), rollback=AsyncMock(), add=Mock())
    service = ChatService(db)
    service._get_v2_channel = AsyncMock(return_value=NS(id="channel-id"))
    service.get_global_commands = AsyncMock(return_value=None)
    service.update_chat_command = AsyncMock(return_value="updated")
    return service, db


@pytest.mark.parametrize("name", ["hello|new", "new|hi", "hello|hi|new"])
@pytest.mark.parametrize("active", [True, False])
def test_overlapping_alias_bundle_is_rejected(name, active):
    existing = command("hello|hi")
    existing.is_active = active
    service, db = registration_service([existing])
    result = asyncio.run(service.add_chat_command("channel", name, "response", "chzzk"))
    assert result[0] == "reserved"
    db.add.assert_not_called()
    service.update_chat_command.assert_not_awaited()


@pytest.mark.parametrize("name", ["hello", "hi", "hello|hi", "hi|hello", " hi | hello ", "hi|hello|hi"])
@pytest.mark.parametrize("active", [True, False])
def test_existing_command_can_still_be_updated_by_alias(name, active):
    existing = command("hello|hi")
    existing.is_active = active
    service, db = registration_service([existing])
    assert asyncio.run(service.add_chat_command("channel", name, "new", "chzzk")) == ("updated", "hello|hi")
    service.update_chat_command.assert_awaited_once_with(
        "channel", "hello|hi", "new", "chzzk", None, None, None,
    )


@pytest.mark.parametrize("name", ["new|공지", "타이머|new", "new|reserved"])
def test_reserved_alias_is_rejected(name):
    service, db = registration_service()
    service.get_global_commands.side_effect = lambda alias: command(alias) if alias == "reserved" else None
    assert asyncio.run(service.add_chat_command("channel", name, "response", "chzzk"))[0] == "reserved"
    db.add.assert_not_called()


def test_new_alias_bundle_is_normalized_and_created():
    service, db = registration_service()
    assert asyncio.run(service.add_chat_command("channel", " hello | hi ", "response", "chzzk")) == ("created", "hello|hi")
    assert db.add.call_args.args[0].command == "hello|hi"
    db.commit.assert_awaited_once()
