import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from typing import cast
from sqlalchemy.ext.asyncio import AsyncSession
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from sqlalchemy.exc import IntegrityError

os.environ.setdefault("CLIENT_SECRET", "test-client-secret")

from app.features.chat import service as service_module
from app.features.chat.service import ChatService, LiveStatusUnavailableError
from app.platforms.base import LiveStatus
from app.redis import redis_service


NOW = datetime(2026, 9, 19, tzinfo=timezone.utc)


def scalar(value):
    return SimpleNamespace(scalar_one_or_none=lambda: value)


def setup_service(monkeypatch):
    db = SimpleNamespace(
        execute=AsyncMock(), commit=AsyncMock(), rollback=AsyncMock(),
        flush=AsyncMock(), get=AsyncMock(return_value=None), add=Mock(),
    )
    service = ChatService(cast(AsyncSession, db))
    service._get_v2_channel = AsyncMock(return_value=SimpleNamespace(id="channel-id"))
    monkeypatch.setattr(service_module.asyncio, "sleep", AsyncMock())
    return service, db


@pytest.mark.parametrize("failure", [
    LiveStatusUnavailableError("unavailable"),
    httpx.ReadTimeout("timeout"),
    IntegrityError("insert", {}, Exception("duplicate")),
])
def test_retry_rolls_back_and_rechecks_existing_attendance(monkeypatch, failure):
    service, db = setup_service(monkeypatch)
    service.sync_stream_session = AsyncMock(side_effect=[failure, SimpleNamespace(opened_at=NOW)])
    existing = SimpleNamespace(last_attendance_at=NOW, attendance_count=7, streak_count=3)
    db.execute.side_effect = [scalar(None), scalar(existing)]

    result = asyncio.run(service.process_attendance("channel", "user", "name", "chzzk"))

    assert result is not None
    assert result["status"] == "already_checked"
    assert result["total"] == 7
    db.rollback.assert_awaited_once()
    db.commit.assert_not_awaited()
    assert service.sync_stream_session.await_count == 2
    assert service.sync_stream_session.await_args is not None
    assert service.sync_stream_session.await_args.kwargs["force_refresh"] is True


def test_retry_exhaustion_is_not_reported_as_offline(monkeypatch):
    service, db = setup_service(monkeypatch)
    service.sync_stream_session = AsyncMock(side_effect=LiveStatusUnavailableError("unavailable"))
    assert asyncio.run(service.process_attendance("channel", "user", "name", "chzzk")) is None
    assert service.sync_stream_session.await_count == 3
    assert db.rollback.await_count == 3
    db.commit.assert_not_awaited()


@pytest.mark.parametrize("previous_attended,expected_streak", [(True, 4), (False, 1)])
def test_new_broadcast_counts_once_and_preserves_streak_rules(monkeypatch, previous_attended, expected_streak):
    service, db = setup_service(monkeypatch)
    service.sync_stream_session = AsyncMock(return_value=SimpleNamespace(opened_at=NOW))
    previous = NOW - timedelta(hours=2)
    attendance = SimpleNamespace(
        last_attendance_at=previous if previous_attended else previous - timedelta(days=1),
        attendance_count=7, streak_count=3, user_name="old",
    )
    db.execute.side_effect = [scalar(SimpleNamespace(opened_at=previous)), scalar(attendance)] * 2
    first = asyncio.run(service.process_attendance("channel", "user", "name", "chzzk"))
    second = asyncio.run(service.process_attendance("channel", "user", "name", "chzzk"))
    assert first is not None
    assert second is not None
    assert first["status"] == "checked"
    assert second["status"] == "already_checked"
    assert attendance.attendance_count == 8
    assert attendance.streak_count == expected_streak
    db.commit.assert_awaited_once()


@pytest.mark.parametrize("status", [None, "UNKNOWN", "OPEN", "CLOSE"])
def test_live_lookup_only_marks_confirmed_close_as_offline(monkeypatch, status):
    service, db = setup_service(monkeypatch)
    cache = SimpleNamespace(get=AsyncMock(return_value=None), set=AsyncMock())
    monkeypatch.setattr(redis_service, "redis_client", cache)
    live = LiveStatus("chzzk", "channel", status) if status else None
    provider = SimpleNamespace(get_live_status=AsyncMock(return_value=live))
    monkeypatch.setattr(service_module, "get_live_provider", lambda platform: provider)
    service._mark_stream_closed = AsyncMock()

    result = asyncio.run(service.process_attendance("channel", "user", "name", "chzzk"))

    if status == "CLOSE":
        assert result == {"status": "not_streaming"}
        provider.get_live_status.assert_awaited_once()
        service._mark_stream_closed.assert_awaited_once()
    else:
        assert result is None
        assert provider.get_live_status.await_count == 3
        service._mark_stream_closed.assert_not_awaited()
        cache.set.assert_not_awaited()


def test_session_creation_collision_is_recovered_by_requery(monkeypatch):
    service, db = setup_service(monkeypatch)
    live = LiveStatus("chzzk", "channel", "OPEN", opened_at=NOW)
    monkeypatch.setattr(service_module, "get_live_provider", lambda platform: SimpleNamespace(
        get_live_status=AsyncMock(return_value=live),
    ))
    monkeypatch.setattr(redis_service, "redis_client", SimpleNamespace(
        get=AsyncMock(return_value=None), set=AsyncMock(),
    ))
    from app.features.chat_overlay.overlay_manager import overlay_manager
    monkeypatch.setattr(overlay_manager, "ensure_raw_client_if_connected", AsyncMock())
    existing = SimpleNamespace(id="session-id", opened_at=NOW)
    db.get.return_value = SimpleNamespace(status="OPEN", current_stream_session_id="session-id")
    db.flush.side_effect = IntegrityError("insert", {}, Exception("duplicate"))
    attendance = SimpleNamespace(last_attendance_at=NOW, attendance_count=1, streak_count=1)
    db.execute.side_effect = [scalar(None), scalar(existing), scalar(None), scalar(attendance)]

    result = asyncio.run(service.process_attendance("channel", "user", "name", "chzzk"))

    assert result is not None
    assert result["status"] == "already_checked"
    db.rollback.assert_awaited_once()
    db.flush.assert_awaited_once()
    assert db.execute.await_count == 4


@pytest.mark.parametrize("result", [None, {"status": "not_streaming"},
                                      {"status": "checked", "total": 7, "streak": 3}])
def test_greeting_never_fabricates_zero_counts(monkeypatch, result):
    from app.core import database
    from app.features.chat.handling import handler
    from app.features.chat.session_manager import session_manager

    monkeypatch.setattr(database, "get_session_factory", lambda: object())
    monkeypatch.setattr(handler, "_redis_service", SimpleNamespace(
        get_command_prefix=AsyncMock(return_value="!"),
        get_greeting_response=AsyncMock(return_value=("총 [출석일]회 / 연속 [연속출석일]회", True)),
    ))
    monkeypatch.setattr(handler, "process_greeting_attendance_with_lock", AsyncMock(return_value=result))
    session = SimpleNamespace(send_chat=AsyncMock())
    monkeypatch.setattr(session_manager, "get_existing_session", lambda channel: session)

    asyncio.run(handler.on_message("channel", "hello", "common_user", "user", "name"))

    message = session.send_chat.await_args.args[0]
    assert message == ("총 7회 / 연속 3회" if result and result["status"] == "checked" else "@name님 안녕하세요!")


def test_cached_open_does_not_call_provider_and_first_attendance_is_recorded(monkeypatch):
    service, db = setup_service(monkeypatch)
    cached = redis_service.RedisConfigService.serialize_live_status(
        LiveStatus("chzzk", "channel", "OPEN", opened_at=NOW),
    )
    monkeypatch.setattr(redis_service, "redis_client", SimpleNamespace(
        get=AsyncMock(return_value=json.dumps(cached)), set=AsyncMock(),
    ))
    provider_factory = Mock(side_effect=AssertionError("cached OPEN should be reused"))
    monkeypatch.setattr(service_module, "get_live_provider", provider_factory)
    from app.features.chat_overlay.overlay_manager import overlay_manager
    monkeypatch.setattr(overlay_manager, "ensure_raw_client_if_connected", AsyncMock())
    db.get.return_value = SimpleNamespace(status="OPEN", current_stream_session_id="session-id")
    db.execute.side_effect = [
        scalar(SimpleNamespace(id="session-id", opened_at=NOW)), scalar(None), scalar(None),
    ]

    result = asyncio.run(service.process_attendance("channel", "user", "name", "chzzk"))

    assert result == {"status": "checked", "total": 1, "streak": 1, "is_new": True}
    assert db.add.call_args.args[0].last_attendance_at == NOW
    provider_factory.assert_not_called()


@pytest.mark.parametrize("custom", [False, True])
def test_exhausted_failure_sends_no_attendance_message(monkeypatch, custom):
    from app.features.chat.handling import attendance

    service = SimpleNamespace(process_attendance=AsyncMock(return_value=None))
    session = SimpleNamespace(send_chat=AsyncMock())
    redis = SimpleNamespace(check_and_set_cooldown=AsyncMock(return_value=False))
    command = SimpleNamespace(command="attendance", cooldown_seconds=5)
    handler = attendance.handle_custom_attendance if custom else attendance.handle_global_attendance

    asyncio.run(handler(session, service, "channel", command, "user", "name", redis))

    session.send_chat.assert_not_awaited()
    assert "channel:user" not in attendance._attendance_in_flight
