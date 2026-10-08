import asyncio
import base64
import os
import struct
import zlib
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from fastapi import FastAPI, HTTPException, Request
from redis.exceptions import ConnectionError as RedisConnectionError
from pydantic import ValidationError
from sqlalchemy import BigInteger, create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

os.environ.setdefault("CLIENT_SECRET", "test-client-secret")

from app.core import config, security
from app.core import database
from app.core.database import get_async_db
from app.db.models import Base, V2Channel, V2DrawingDonationSetting, V2DonationDrawing, V2DrawingDonationQueue
from app.features.drawing_donation.router import drawing_router
from app.features.drawing_donation.schemas import MAX_FINAL_PNG_LENGTH, DrawingSaveRequest, Recording, Stroke
from app.features.drawing_donation.service import DrawingDonationService, drawing_tags
from app.features.chat.handling import events
from app.features.drawing_donation.cleanup import DrawingDonationCleanup
from app.features.drawing_donation import limits
from app.features.drawing_donation import live_background, router as drawing_routes
from app.exception_handlers import register_exception_handlers


# SQLite is a local persistence fixture; PostgreSQL row locking is checked separately.
@compiles(JSONB, "sqlite")
def compile_jsonb(type_, compiler, **kwargs):
    return "JSON"


@compiles(BigInteger, "sqlite")
def compile_bigint(type_, compiler, **kwargs):
    return "INTEGER"


class LocalDB:
    def __init__(self, session):
        self.session = session

    async def execute(self, query):
        return self.session.execute(query)

    async def get(self, model, key):
        return self.session.get(model, key)

    def add(self, obj):
        self.session.add(obj)

    async def commit(self):
        self.session.commit()

    async def rollback(self):
        self.session.rollback()


def png(width=800, height=600):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    raw = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    raw += chunk(b"IDAT", zlib.compress((b"\0" + b"\xff" * (width * 3)) * height)) + chunk(b"IEND", b"")
    return "data:image/png;base64," + base64.b64encode(raw).decode()


def save_payload(**changes):
    data = {"save_key": str(uuid4()), "final_png": png(), "recording": {"actions": [
        {"type": "stroke", "tool": "pen", "width": 6, "color": "#246544", "points": [
            {"x": 10, "y": 10, "t": 0}, {"x": 120, "y": 80, "t": 1000}]},
        {"type": "undo", "t": 1100},
        {"type": "stroke", "tool": "pen", "width": 4, "color": "#dfa348", "points": [{"x": 200, "y": 200, "t": 1200}]},
    ]}}
    data.update(changes)
    return data


@pytest.fixture
def db():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine, tables=[V2Channel.__table__, V2DrawingDonationSetting.__table__,
                                           V2DonationDrawing.__table__, V2DrawingDonationQueue.__table__])
    with Session(engine, expire_on_commit=False) as session:
        for name in ["channel", "other"]:
            session.add(V2Channel(id=uuid4(), platform="chzzk", platform_channel_id=name, channel_name=name))
        session.commit()
        yield LocalDB(session)
    engine.dispose()


async def enabled(db, channel="channel"):
    service = DrawingDonationService(db)
    _, setting = await service.setting(channel, create=True)
    setting.options = {**setting.options, "enabled": True}
    await db.commit()
    return service, setting


def donation(tag, **changes):
    return {"donationText": f"그림 보냅니다 {tag}!", "payAmount": "1000", "donatorNickname": "시청자", **changes}


def test_saved_drawing_is_immutable_and_retry_returns_same_tag(db):
    async def run():
        service, _ = await enabled(db)
        payload = DrawingSaveRequest.model_validate(save_payload())
        before_save = datetime.now(timezone.utc)
        first = await service.save_drawing("channel", payload)
        assert before_save + timedelta(hours=1) <= first.expires_at <= datetime.now(timezone.utc) + timedelta(hours=1)
        second = await service.save_drawing("channel", payload)
        assert first.id == second.id
        assert drawing_tags(first.hashtag) == [first.hashtag]
        assert first.recording == payload.recording.model_dump()
        assert first.final_png == ""
        assert len(db.session.scalars(select(V2DonationDrawing)).all()) == 1
    asyncio.run(run())


@pytest.mark.parametrize("width,height", [(400, 300), (1280, 720), (1920, 1080)])
def test_configured_canvas_size_is_saved_and_replayed(db, width, height):
    async def run():
        service, setting = await enabled(db)
        setting.options = {**setting.options, "canvas_width": width, "canvas_height": height}
        await db.commit()
        data = save_payload(final_png=png(width, height))
        data["recording"].update(width=width, height=height)
        drawing = await service.save_drawing("channel", DrawingSaveRequest.model_validate(data))
        assert await service.enqueue_donation("channel", donation(drawing.hashtag)) is not None
        playback = (await service.next_playback(setting.overlay_token))["playback"]
        assert (playback["recording"]["width"], playback["recording"]["height"]) == (width, height)
        assert "final_png" not in playback
    asyncio.run(run())


def test_canvas_changes_keep_saved_drawings_and_legacy_settings_usable(db):
    async def run():
        service, setting = await enabled(db)
        setting.options = {**setting.options, "display_width": 600, "show_donor": False}
        await db.commit()
        payload = DrawingSaveRequest.model_validate(save_payload())
        old = await service.save_drawing("channel", payload)
        job = await service.enqueue_donation("channel", donation(old.hashtag))
        assert job is not None
        assert (await service.next_playback(setting.overlay_token))["playback"]["options"]["show_donor"] is False
        assert job.playback is not None
        job.playback = {**job.playback, "display_width": 600}
        setting.options = {**setting.options, "canvas_width": 1280, "canvas_height": 720}
        await db.commit()
        assert (await service.save_drawing("channel", payload)).hashtag == old.hashtag
        with pytest.raises(HTTPException) as exc:
            await service.save_drawing("channel", DrawingSaveRequest.model_validate(save_payload()))
        assert exc.value.status_code == 409
        resumed = (await service.next_playback(setting.overlay_token))["playback"]
        assert resumed["recording"]["width"] == 800 and resumed["recording"]["height"] == 600
        assert "display_width" not in resumed["options"]
    asyncio.run(run())


def test_canvas_limits_and_png_recording_size_mismatch_are_rejected():
    from app.features.drawing_donation.schemas import DrawingDonationOptions
    fill_data = save_payload()
    fill_data["recording"]["actions"][0].update(tool="fill", points=[{"x": 10, "y": 10, "t": 0}])
    fill_action = DrawingSaveRequest.model_validate(fill_data).recording.actions[0]
    assert isinstance(fill_action, Stroke) and fill_action.tool == "fill"
    for change in [{"canvas_width": 1921}, {"canvas_height": 1081}]:
        with pytest.raises(ValidationError):
            DrawingDonationOptions.model_validate(change)
    data = save_payload(final_png=png(1280, 720))
    with pytest.raises(ValidationError):
        DrawingSaveRequest.model_validate(data)
    data["recording"].update(width=1280, height=720)
    data["recording"]["actions"][0]["points"][0]["x"] = 1281
    with pytest.raises(ValidationError):
        DrawingSaveRequest.model_validate(data)
    oversized = save_payload(final_png="x" * (MAX_FINAL_PNG_LENGTH + 1))
    with pytest.raises(ValidationError):
        DrawingSaveRequest.model_validate(oversized)


def test_donation_event_handler_registers_drawing_each_time(db, monkeypatch):
    monkeypatch.setattr(events, "get_channel_logger", lambda name: Mock())
    @asynccontextmanager
    async def factory():
        yield db
    monkeypatch.setattr(database, "get_session_factory", lambda: factory)
    async def run():
        service, _ = await enabled(db)
        drawing = await service.save_drawing("channel", DrawingSaveRequest.model_validate(save_payload()))
        for _ in range(2):
            await events.on_donation("channel", donation(drawing.hashtag))
        assert len(db.session.scalars(select(V2DrawingDonationQueue)).all()) == 2
    asyncio.run(run())


def test_postgresql_overlay_query_locks_setting_row(db, monkeypatch):
    async def run():
        service, setting = await enabled(db)
        execute, queries = db.execute, []
        async def capture(query):
            queries.append(str(query.compile(dialect=postgresql.dialect())))
            return await execute(query)
        monkeypatch.setattr(db, "execute", capture)
        await service.overlay_setting(setting.overlay_token, lock=True)
        assert "FOR UPDATE OF v2_drawing_donation_settings" in queries[0]
    asyncio.run(run())


def test_retention_deletes_png_recording_and_all_queue_states_but_keeps_settings(db):
    async def run():
        service, setting = await enabled(db)
        now = datetime.now(timezone.utc)
        expired = await service.save_drawing("channel", DrawingSaveRequest.model_validate(save_payload()))
        fresh = await service.save_drawing("channel", DrawingSaveRequest.model_validate(save_payload()))
        jobs = [await service.enqueue_donation("channel", donation(expired.hashtag)) for _ in range(3)]
        for job, status in zip(jobs, ["queued", "playing", "done"]):
            assert job is not None
            job.status = status
        fresh_job = await service.enqueue_donation("channel", donation(fresh.hashtag))
        assert fresh_job is not None
        expired.expires_at = now
        fresh.expires_at = now + timedelta(seconds=1)
        await db.commit()
        assert await service.delete_expired_drawings(now=now) == 1
        assert db.session.scalars(select(V2DonationDrawing)).all() == [fresh]
        assert db.session.scalars(select(V2DrawingDonationQueue)).all() == [fresh_job]
        assert await db.get(V2DrawingDonationSetting, setting.channel_id) is setting
        assert await service.delete_expired_drawings(now=now) == 0
    asyncio.run(run())


@pytest.mark.parametrize("playing", [False, True])
def test_expired_drawing_is_not_replayed_even_before_cleanup_runs(db, playing):
    async def run():
        service, setting = await enabled(db)
        expired = await service.save_drawing("channel", DrawingSaveRequest.model_validate(save_payload()))
        fresh = await service.save_drawing("channel", DrawingSaveRequest.model_validate(save_payload()))
        job = await service.enqueue_donation("channel", donation(expired.hashtag))
        assert job is not None
        if playing:
            assert (await service.next_playback(setting.overlay_token))["current_id"] == str(job.id)
        expired.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await db.commit()
        assert (await service.next_playback(setting.overlay_token, str(job.id)))["current_id"] is None
        fresh_job = await service.enqueue_donation("channel", donation(fresh.hashtag))
        assert fresh_job is not None
        assert (await service.next_playback(setting.overlay_token))["current_id"] == str(fresh_job.id)
        assert await service.delete_expired_drawings() == 1
    asyncio.run(run())


def test_cleanup_batches_and_rejects_expired_save_retries(db):
    async def run():
        service, _ = await enabled(db)
        payload = DrawingSaveRequest.model_validate(save_payload())
        old = await service.save_drawing("channel", payload)
        drawings = [old] + [await service.save_drawing("channel", DrawingSaveRequest.model_validate(save_payload())) for _ in range(2)]
        for drawing in drawings:
            drawing.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await db.commit()
        with pytest.raises(HTTPException) as exc:
            await service.save_drawing("channel", payload)
        assert exc.value.status_code == 410
        assert await service.delete_expired_drawings(batch_size=2) == 2
        assert await service.delete_expired_drawings(batch_size=2) == 1
        assert not db.session.scalars(select(V2DonationDrawing)).all()
    asyncio.run(run())


def test_cleanup_worker_drains_multiple_batches_and_returns_sessions(db):
    async def run():
        _, setting = await enabled(db)
        for i in range(251):
            db.add(V2DonationDrawing(
                channel_id=setting.channel_id, save_key=uuid4(), hashtag="#mw-" + format(i, "024x"),
                recording={}, final_png="expired-image", expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
            ))
        await db.commit()
        sessions = []
        @asynccontextmanager
        async def factory():
            sessions.append("opened")
            try:
                yield db
            finally:
                sessions.append("closed")
        assert await DrawingDonationCleanup(factory).cleanup_once() == 251
        assert sessions == ["opened", "closed", "opened", "closed"]
        assert not db.session.scalars(select(V2DonationDrawing)).all()
    asyncio.run(run())


def test_cleanup_runs_on_start_retries_failure_and_stops():
    async def run():
        cleanup = DrawingDonationCleanup(Mock())
        cleanup.interval_seconds = 0.001
        async def finished():
            cleanup.stop()
            return 1
        calls = 0
        async def attempt():
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("temporary")
            return await finished()
        cleanup.cleanup_once = AsyncMock(side_effect=attempt)
        await asyncio.wait_for(cleanup.run(), timeout=1)
        assert cleanup.cleanup_once.await_count == 2
        await cleanup.run()
        assert cleanup.cleanup_once.await_count == 2
    asyncio.run(run())


def test_same_tag_replays_on_each_donation_in_fifo_order(db):
    async def run():
        service, setting = await enabled(db)
        drawing = await service.save_drawing("channel", DrawingSaveRequest.model_validate(save_payload()))
        first = await service.enqueue_donation("channel", donation(drawing.hashtag, donatorNickname="첫 후원"))
        second = await service.enqueue_donation("channel", donation(drawing.hashtag, donatorNickname="두 번째"))
        assert first is not None and second is not None
        assert first.id != second.id
        playback = await service.next_playback(setting.overlay_token)
        assert playback["playback"]["nickname"] == "첫 후원"
        assert "final_png" not in playback["playback"]
        # A second OBS connection receives the same active picture, never consumes the next job.
        repeated = await service.next_playback(setting.overlay_token)
        assert repeated["playback"]["id"] == str(first.id)
        lightweight = await service.next_playback(setting.overlay_token, str(first.id))
        assert lightweight["current_id"] == str(first.id) and lightweight["playback"] is None
        first.started_at = datetime.now(timezone.utc) - timedelta(minutes=3)
        await db.commit()
        next_picture = await service.next_playback(setting.overlay_token)
        assert first.status == "done"
        assert next_picture["playback"]["id"] == str(second.id)
    asyncio.run(run())


@pytest.mark.parametrize("amount", ["999", "-1000", "1e4", "1000.0", None, True])
def test_donation_amount_is_validated_before_queueing(db, amount):
    async def run():
        service, _ = await enabled(db)
        drawing = await service.save_drawing("channel", DrawingSaveRequest.model_validate(save_payload()))
        assert await service.enqueue_donation("channel", donation(drawing.hashtag, payAmount=amount)) is None
        assert not db.session.scalars(select(V2DrawingDonationQueue)).all()
    asyncio.run(run())


def test_other_channel_expired_tags_and_disabled_channel_do_not_queue(db):
    async def run():
        service, setting = await enabled(db)
        await enabled(db, "other")
        drawing = await service.save_drawing("channel", DrawingSaveRequest.model_validate(save_payload()))
        assert await service.enqueue_donation("other", donation(drawing.hashtag)) is None
        drawing.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await db.commit()
        assert await service.enqueue_donation("channel", donation(drawing.hashtag)) is None
        drawing.expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        setting.options = {**setting.options, "enabled": False}
        await db.commit()
        assert await service.enqueue_donation("channel", donation(drawing.hashtag)) is None
        assert (await service.next_playback(setting.overlay_token))["playback"] is None
    asyncio.run(run())


def test_tag_matching_requires_complete_tag_and_ignores_duplicate_mentions():
    tag = "#mw-" + "ab" * 12
    assert drawing_tags(f"안녕 {tag.upper()}!\n{tag}") == [tag]
    assert drawing_tags(f"prefix{tag} {tag}xxx ##{tag[1:]}") == []
    assert drawing_tags(None) == []


@pytest.mark.parametrize("field,value", [("x", 801), ("y", -1), ("t", 600001), ("x", float("nan"))])
def test_invalid_recording_coordinates_are_rejected(field, value):
    data = save_payload()["recording"]
    data["actions"][0]["points"][0][field] = value
    with pytest.raises(ValidationError):
        Recording.model_validate(data)


def test_backwards_recording_and_invalid_png_are_rejected():
    data = save_payload()
    data["recording"]["actions"][1]["t"] = 2
    with pytest.raises(ValidationError):
        DrawingSaveRequest.model_validate(data)
    with pytest.raises(ValidationError):
        DrawingSaveRequest.model_validate(save_payload(final_png="data:image/svg+xml,<svg/>"))


def test_http_flow_requires_owner_login_and_private_overlay_token(db, monkeypatch):
    monkeypatch.setattr(limits, "redis_client", Mock(eval=AsyncMock(return_value=0)))
    monkeypatch.setattr(config, "ADMIN_TOKEN", "test-drawing-secret")
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(drawing_router)
    async def local_db():
        yield db
    app.dependency_overrides[get_async_db] = local_db
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.get("/auth/dashboard/drawing")).status_code == 401
            client.cookies.set("dashboard_session", security.create_dashboard_session_token("channel"))
            assert (await client.get("/auth/dashboard/drawing")).status_code == 200
            response = await client.post("/auth/dashboard/drawing", json={"enabled": True})
            assert response.status_code == 200
            client.cookies.clear()
            assert (await client.get("/drawing/chzzk/channel")).status_code == 200
            response = await client.post("/drawing/chzzk/channel", json=save_payload())
            assert response.status_code == 200
            tag = response.json()["hashtag"]
            service = DrawingDonationService(db)
            await service.enqueue_donation("channel", donation(tag))
            _, setting = await service.setting("channel")
            assert setting is not None
            assert (await client.post("/drawing/overlay/wrong-token/next")).status_code == 404
            assert (await client.post(f"/drawing/overlay/{setting.overlay_token}/next")).json()["playback"]["hashtag"] == tag
            assert (await client.post("/auth/dashboard/drawing", json={"enabled": False})).status_code == 401
    asyncio.run(run())


@pytest.fixture
def save_redis(monkeypatch):
    fakeredis = pytest.importorskip("fakeredis.aioredis")
    pytest.importorskip("lupa")
    client = fakeredis.FakeRedis(server=pytest.importorskip("fakeredis").FakeServer(), decode_responses=True)
    monkeypatch.setattr(limits, "redis_client", client)
    monkeypatch.setattr(config, "DRAWING_DONATION_TRUST_PROXY_HEADERS", False)
    return client


def save_app(db):
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(drawing_router)
    async def local_db():
        yield db
    app.dependency_overrides[get_async_db] = local_db
    return app


def test_new_save_keys_and_channel_switching_cannot_bypass_ip_limit(db, monkeypatch, save_redis):
    monkeypatch.setattr(config, "DRAWING_DONATION_SAVE_PER_MINUTE", 2)
    async def run():
        await enabled(db)
        await enabled(db, "other")
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=save_app(db)), base_url="http://test") as client:
            for channel in ["channel", "other"]:
                assert (await client.post(f"/drawing/chzzk/{channel}", json=save_payload())).status_code == 200
            response = await client.post("/drawing/chzzk/channel", json=save_payload(),
                                         headers={"X-Real-IP": "203.0.113.1", "X-Forwarded-For": "203.0.113.2"})
            assert response.status_code == 429
            assert 1 <= int(response.headers["Retry-After"]) <= 60
            assert "요청이 너무 많습니다" in response.json()["error"]
            assert len(db.session.scalars(select(V2DonationDrawing)).all()) == 2
        await save_redis.aclose()
    asyncio.run(run())


def test_concurrent_requests_share_limit_without_extending_window(monkeypatch, save_redis):
    monkeypatch.setattr(config, "DRAWING_DONATION_SAVE_PER_MINUTE", 3)
    async def run():
        request = Request({"type": "http", "client": ("203.0.113.1", 1), "headers": []})
        results = await asyncio.gather(*[limits.limit_save_requests(request) for _ in range(20)], return_exceptions=True)
        assert sum(result is None for result in results) == 3
        assert all(isinstance(result, HTTPException) and result.status_code == 429 for result in results if result)
        minute_key = (await save_redis.keys("drawing:save:ip:minute:*"))[0]
        hour_key = (await save_redis.keys("drawing:save:ip:hour:*"))[0]
        await save_redis.expire(minute_key, 5)
        with pytest.raises(HTTPException) as exc:
            await limits.limit_save_requests(request)
        assert exc.value.headers is not None
        assert 1 <= int(exc.value.headers["Retry-After"]) <= 5
        assert int(await save_redis.get(hour_key)) == 3
        # 1분 제한이 끝나도 시간 제한의 누적값은 유지한다.
        await save_redis.delete(minute_key)
        await limits.limit_save_requests(request)
        assert int(await save_redis.get(hour_key)) == 4
        await save_redis.aclose()
    asyncio.run(run())


def test_hourly_limit_survives_short_window_and_client_changes(monkeypatch, save_redis):
    monkeypatch.setattr(config, "DRAWING_DONATION_SAVE_PER_MINUTE", 5)
    monkeypatch.setattr(config, "DRAWING_DONATION_SAVE_PER_HOUR", 2)
    async def run():
        request = Request({"type": "http", "client": ("203.0.113.1", 1), "headers": []})
        await limits.limit_save_requests(request)
        await limits.limit_save_requests(request)
        minute_key = (await save_redis.keys("drawing:save:ip:minute:*"))[0]
        await save_redis.delete(minute_key)
        # 다른 프로세스에 해당하는 새 Redis 연결에서도 같은 누적값을 확인한다.
        connection_kwargs = save_redis.connection_pool.connection_kwargs
        assert connection_kwargs is not None
        other = type(save_redis)(server=connection_kwargs["server"], decode_responses=True)
        monkeypatch.setattr(limits, "redis_client", other)
        with pytest.raises(HTTPException) as exc:
            await limits.limit_save_requests(request)
        assert exc.value.status_code == 429
        assert exc.value.headers is not None
        assert 1 <= int(exc.value.headers["Retry-After"]) <= 3600
        assert not await other.exists(minute_key)
        await other.aclose()
        await save_redis.aclose()
    asyncio.run(run())


def test_global_byte_budget_blocks_different_ips_before_saving(db, monkeypatch, save_redis):
    import json
    first, second = save_payload(), save_payload()
    body = json.dumps(first).encode()
    monkeypatch.setattr(config, "DRAWING_DONATION_SAVE_BYTE_BUDGET", len(body))
    async def run():
        await enabled(db)
        app = save_app(db)
        for ip, payload in [("203.0.113.1", body), ("203.0.113.2", json.dumps(second).encode())]:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=(ip, 1)), base_url="http://test") as client:
                response = await client.post("/drawing/chzzk/channel", content=payload)
                assert response.status_code == (200 if ip.endswith("1") else 429)
        assert len(db.session.scalars(select(V2DonationDrawing)).all()) == 1
        assert int(await save_redis.get("drawing:save:bytes")) == len(body)
        await save_redis.aclose()
    asyncio.run(run())


@pytest.mark.parametrize("failure_stage", ["requests", "bytes"])
def test_redis_failure_prevents_save(db, monkeypatch, failure_stage):
    replies = [RedisConnectionError("unavailable")] if failure_stage == "requests" else [0, RedisConnectionError("unavailable")]
    monkeypatch.setattr(limits, "redis_client", Mock(eval=AsyncMock(side_effect=replies)))
    async def run():
        await enabled(db)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=save_app(db)), base_url="http://test") as client:
            response = await client.post("/drawing/chzzk/channel", json=save_payload())
        assert response.status_code == 503
        assert response.headers["Retry-After"] == "30"
        assert "잠시 후 다시 시도" in response.json()["error"]
        assert not db.session.scalars(select(V2DonationDrawing)).all()
    asyncio.run(run())


def test_request_limit_rejects_before_body_is_read(monkeypatch):
    monkeypatch.setattr(limits, "redis_client", Mock(eval=AsyncMock(return_value=60)))
    async def run():
        async def receive():
            pytest.fail("차단된 저장 요청의 본문을 읽으면 안 됩니다.")
        request = Request({"type": "http", "client": ("203.0.113.1", 1), "headers": []}, receive=receive)
        from app.features.drawing_donation.router import save_drawing
        with pytest.raises(HTTPException) as exc:
            await save_drawing("channel", request, db=Mock())
        assert exc.value.status_code == 429
    asyncio.run(run())


def test_proxy_ip_is_only_used_when_explicitly_trusted(monkeypatch):
    request = Request({"type": "http", "client": ("172.18.0.2", 1), "headers": [
        (b"x-real-ip", b"203.0.113.1"), (b"x-forwarded-for", b"203.0.113.2")]})
    monkeypatch.setattr(config, "DRAWING_DONATION_TRUST_PROXY_HEADERS", False)
    assert limits.client_address(request) == "172.18.0.2"
    monkeypatch.setattr(config, "DRAWING_DONATION_TRUST_PROXY_HEADERS", True)
    assert limits.client_address(request) == "203.0.113.1"
    invalid = Request({"type": "http", "client": ("172.18.0.2", 1), "headers": [(b"x-real-ip", b"spoofed")]})
    assert limits.client_address(invalid) == "172.18.0.2"


@pytest.mark.parametrize("payload,expected", [
    ({"content": {"liveImageUrl": "https://thumbnail.example/image_{type}.jpg"}}, "https://thumbnail.example/image_720.jpg"),
    ({"content": {"liveImageUrl": "https://thumbnail.example/image_720.jpg"}}, "https://thumbnail.example/image_720.jpg"),
    ({"content": None}, None),
    ({"content": {"liveImageUrl": None}}, None),
    ({"content": {"liveImageUrl": 123}}, None),
    ({"content": {"liveImageUrl": "javascript:alert(1)"}}, None),
    ({"content": {"liveImageUrl": "https://user:password@thumbnail.example/image.jpg"}}, None),
    ([], None),
])
def test_live_background_uses_720_and_handles_missing_or_invalid_urls(monkeypatch, payload, expected):
    def upstream(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://api.chzzk.naver.com/service/v3/channels/channel/live-detail"
        assert request.headers["Origin"] == "https://chzzk.naver.com"
        return httpx.Response(200, json=payload)
    client_class = httpx.AsyncClient
    monkeypatch.setattr(live_background.httpx, "AsyncClient", lambda **kwargs:
                        client_class(transport=httpx.MockTransport(upstream), **kwargs))
    assert asyncio.run(live_background.get_live_background_url("channel")) == expected


@pytest.mark.parametrize("failure", ["timeout", "http", "json"])
def test_live_background_upstream_failure_returns_no_image(monkeypatch, failure):
    def upstream(request: httpx.Request) -> httpx.Response:
        if failure == "timeout":
            raise httpx.ReadTimeout("timeout", request=request)
        return httpx.Response(502 if failure == "http" else 200, content=b"not-json")
    client_class = httpx.AsyncClient
    monkeypatch.setattr(live_background.httpx, "AsyncClient", lambda **kwargs:
                        client_class(transport=httpx.MockTransport(upstream), **kwargs))
    assert asyncio.run(live_background.get_live_background_url("channel")) is None


def test_live_background_endpoint_enforces_channel_and_rate_limit(db, monkeypatch, save_redis):
    fetch = AsyncMock(return_value="https://thumbnail.example/image_720.jpg")
    monkeypatch.setattr(drawing_routes, "get_live_background_url", fetch)
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=save_app(db)), base_url="http://test") as client:
            assert (await client.get("/drawing/chzzk/missing/background")).status_code == 404
            assert (await client.get("/drawing/chzzk/channel/background")).status_code == 403
            fetch.assert_not_awaited()
            await enabled(db)
            await enabled(db, "other")
            response = await client.get("/drawing/chzzk/channel/background")
            assert response.status_code == 200
            assert response.json()["image_url"] == fetch.return_value
            assert response.headers["Cache-Control"] == "no-store"
            responses = await asyncio.gather(*[client.get("/drawing/chzzk/other/background") for _ in range(3)])
            for response in responses:
                assert response.status_code == 429
                assert 1 <= int(response.headers["Retry-After"]) <= 5
                assert "방송 이미지" in response.json()["error"]
            fetch.assert_awaited_once_with("channel")
            assert not await save_redis.keys("drawing:save:*")
            for key in await save_redis.keys("drawing:background:*"):
                await save_redis.delete(key)
            assert (await client.get("/drawing/chzzk/other/background")).status_code == 200
            await save_redis.aclose()
    asyncio.run(run())


def test_live_background_limit_failure_does_not_call_upstream(db, monkeypatch):
    fetch = AsyncMock()
    monkeypatch.setattr(drawing_routes, "get_live_background_url", fetch)
    monkeypatch.setattr(limits, "redis_client", Mock(eval=AsyncMock(side_effect=RedisConnectionError("unavailable"))))
    async def run():
        await enabled(db)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=save_app(db)), base_url="http://test") as client:
            response = await client.get("/drawing/chzzk/channel/background")
            assert response.status_code == 503
            assert "방송 이미지" in response.json()["error"]
            assert response.headers["Retry-After"] == "30"
            assert (await client.get("/drawing/chzzk/channel")).status_code == 200
        fetch.assert_not_awaited()
    asyncio.run(run())
