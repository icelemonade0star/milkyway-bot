import asyncio
import json
import os
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, MagicMock, Mock

import httpx
import pytest
import socketio
from aiohttp import web

os.environ.setdefault("CLIENT_SECRET", "test-client-secret")

from app.features.chat.clients import chat_client
from app.features.chat.handling import events
from app.features.chat import session_manager, session_watchdog
from app.core import database
from app.platforms.chzzk import chat


@pytest.fixture(autouse=True)
def no_log_files(monkeypatch):
    monkeypatch.setattr(chat_client, "get_channel_logger", lambda name: Mock())
    monkeypatch.setattr(events, "get_channel_logger", lambda name: Mock())


async def emit(client, event, payload):
    await client.socketio.handlers["/"][event](payload)


def system(kind, event="CHAT", channel="channel"):
    return {"type": kind, "data": {"eventType": event, "channelId": channel}}


def make_session():
    session = chat.ChzzkSessions("channel")
    session.access_token = "test-access-token"
    session.session_key = "session-key"
    session.socket_client = chat_client.ChzzkChatClient("name", "channel", on_reconnect=session._on_reconnect)
    session.socket_client.session_key = session.session_key
    return session


@pytest.mark.parametrize("event", ["DONATION", "SUBSCRIPTION"])
@pytest.mark.parametrize("as_json", [False, True])
def test_events_reach_separate_handlers_without_losing_fields(monkeypatch, event, as_json):
    donation, subscription, message = AsyncMock(), AsyncMock(), AsyncMock()
    monkeypatch.setattr(events, "on_donation", donation)
    monkeypatch.setattr(events, "on_subscription", subscription)
    monkeypatch.setattr(chat_client.handler, "on_message", message)
    payload = {
        "channelId": "channel", "donatorChannelId": None, "donatorNickname": "익명",
        "payAmount": "1000", "donationText": "그림", "donationType": "CHAT",
        "subscriberChannelId": "viewer", "subscriberNickname": "시청자",
        "tierNo": 2, "tierName": "브랜드", "month": 3, "extra": {"future": True},
    }
    asyncio.run(emit(make_session().socket_client, event, json.dumps(payload) if as_json else payload))
    selected = donation if event == "DONATION" else subscription
    other = subscription if event == "DONATION" else donation
    selected.assert_awaited_once_with("channel", payload)
    other.assert_not_awaited()
    message.assert_not_awaited()


@pytest.mark.parametrize("event", ["SYSTEM", "CHAT", "DONATION", "SUBSCRIPTION"])
@pytest.mark.parametrize("payload", ["{", "[]", None, {"type": [], "data": {}}, {"channelId": "other"}])
def test_bad_payloads_and_other_channels_are_ignored(monkeypatch, event, payload):
    donation, subscription, message = AsyncMock(), AsyncMock(), AsyncMock()
    monkeypatch.setattr(events, "on_donation", donation)
    monkeypatch.setattr(events, "on_subscription", subscription)
    monkeypatch.setattr(chat_client.handler, "on_message", message)
    asyncio.run(emit(make_session().socket_client, event, payload))
    donation.assert_not_awaited()
    subscription.assert_not_awaited()
    message.assert_not_awaited()


@pytest.mark.parametrize("encoding", ["dict", "json", "bytes"])
@pytest.mark.parametrize("role_location", ["root", "profile"])
def test_chat_still_routes_with_official_and_legacy_role_fields(monkeypatch, encoding, role_location):
    message = AsyncMock()
    monkeypatch.setattr(chat_client.handler, "on_message", message)
    payload = {"channelId": "channel", "senderChannelId": "viewer", "content": "!타이머",
               "profile": {"nickname": "시청자"}}
    (payload if role_location == "root" else payload["profile"])["userRoleCode"] = "streamer"
    data = payload if encoding == "dict" else json.dumps(payload, ensure_ascii=False)
    if encoding == "bytes":
        data = data.encode("utf-8")
    asyncio.run(emit(make_session().socket_client, "CHAT", data))
    message.assert_awaited_once_with("channel", "!타이머", "streamer", user_id="viewer", user_name="시청자")


def test_chat_filters_configured_bots_and_keeps_receiving_after_bad_data(monkeypatch):
    message = AsyncMock()
    monkeypatch.setattr(chat_client.handler, "on_message", message)
    monkeypatch.setattr(chat_client.config, "BOT_NICKNAMES", ["테스트봇"])
    async def run():
        client = make_session().socket_client
        await emit(client, "CHAT", "{")
        await emit(client, "CHAT", {"content": "!명령어", "profile": None})
        await emit(client, "CHAT", {"content": "!명령어", "profile": {"nickname": "테스트봇"}})
        await emit(client, "CHAT", {"content": "안녕하세요", "senderChannelId": "viewer",
                                   "profile": {"nickname": "시청자"}})
    asyncio.run(run())
    message.assert_awaited_once_with("channel", "안녕하세요", None, user_id="viewer", user_name="시청자")


@pytest.mark.parametrize("force_recreate", [False, True])
def test_chat_command_is_available_while_optional_subscriptions_are_pending(monkeypatch, force_recreate):
    async def run():
        session = make_session()
        manager = session_manager.SessionManager()
        old_session = NS(socket_client=NS(disconnect=AsyncMock()))
        if force_recreate:
            manager.add_session("channel", old_session)
        session.create_session = AsyncMock()
        session.socket_url = "https://example.test/socket"
        monkeypatch.setattr(session_manager, "ChzzkSessions", lambda channel: session)
        monkeypatch.setattr(session_manager, "session_manager", manager)
        monkeypatch.setattr(chat_client.handler, "_redis_service", NS(get_command_prefix=AsyncMock(return_value="!")))
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value="db")
        context.__aexit__ = AsyncMock(return_value=False)
        monkeypatch.setattr(database, "get_session_factory", lambda: lambda: context)
        command = AsyncMock()
        monkeypatch.setattr(chat_client.handler, "on_command", command)
        async def respond(request):
            event = request.url.path.rsplit("/", 1)[1].upper()
            if event == "DONATION":
                if force_recreate:
                    old_session.socket_client.disconnect.assert_awaited_once()
                await emit(session.socket_client, "CHAT", {
                    "channelId": "channel", "senderChannelId": "viewer", "content": "!명령어",
                    "userRoleCode": "common_user", "profile": {"nickname": "시청자"},
                })
            await emit(session.socket_client, "SYSTEM", system("subscribed", event))
            return httpx.Response(200)
        async with httpx.AsyncClient(base_url="https://example.test", transport=httpx.MockTransport(respond)) as http:
            monkeypatch.setattr(chat, "_client", http)
            await manager.get_or_create_session("channel", force_recreate=force_recreate)
        command.assert_awaited_once()
        assert command.await_args.args[1] is session
    asyncio.run(run())


def test_system_tracks_confirmation_unsubscribe_and_revocation():
    async def run():
        client = make_session().socket_client
        await emit(client, "SYSTEM", system("subscribed", "DONATION", "other"))
        assert not client.subscribed_events
        for event in chat_client.EVENT_TYPES:
            await emit(client, "SYSTEM", json.dumps(system("subscribed", event)))
        assert client.subscribed_events == set(chat_client.EVENT_TYPES)
        await emit(client, "SYSTEM", system("unsubscribed", "DONATION"))
        await emit(client, "SYSTEM", system("revoked", "SUBSCRIPTION"))
        assert client.subscribed_events == {"CHAT"}
        assert client.denied_events == {"SUBSCRIPTION"}
        await emit(client, "SYSTEM", system("subscribed", "SUBSCRIPTION"))
        assert not client.denied_events
        await client.socketio.handlers["/"]["disconnect"]()
        assert not client.subscribed_events
    asyncio.run(run())


def test_initial_connection_resolves_future_and_reconnect_calls_restore():
    async def run():
        ready, restore = asyncio.Future(), AsyncMock()
        client = chat_client.ChzzkChatClient("name", "channel", ready, restore)
        await emit(client, "SYSTEM", {"type": "connected", "data": {"sessionKey": "first"}})
        assert await ready == "first"
        restore.assert_not_awaited()
        client.subscribed_events.add("CHAT")
        await emit(client, "SYSTEM", {"type": "connected", "data": {"sessionKey": "second"}})
        restore.assert_awaited_once_with("second")
        assert client.session_key == "second"
        assert not client.subscribed_events
    asyncio.run(run())


def test_all_subscriptions_use_same_session_and_user_token(monkeypatch):
    async def run():
        session = make_session()
        requests = []
        async def respond(request):
            requests.append(request)
            event = request.url.path.rsplit("/", 1)[1].upper()
            await emit(session.socket_client, "SYSTEM", system("subscribed", event))
            return httpx.Response(200, json={})
        async with httpx.AsyncClient(base_url="https://example.test", transport=httpx.MockTransport(respond)) as http:
            monkeypatch.setattr(chat, "_client", http)
            assert await session.subscribe_events() == dict.fromkeys(chat_client.EVENT_TYPES, True)
            assert await session.subscribe_events() == dict.fromkeys(chat_client.EVENT_TYPES, True)
        assert [r.url.path for r in requests] == [
            f"/open/v1/sessions/events/subscribe/{event.lower()}" for event in chat_client.EVENT_TYPES]
        assert all(r.method == "POST" and r.url.params["sessionKey"] == "session-key" for r in requests)
        assert all(r.headers["Authorization"] == "Bearer test-access-token" for r in requests)
    asyncio.run(run())


@pytest.mark.parametrize("failure", [403, 500, "network"])
def test_optional_failure_preserves_chat_and_other_event(monkeypatch, failure):
    async def run():
        session = make_session()
        requests = []
        async def respond(request):
            event = request.url.path.rsplit("/", 1)[1].upper()
            requests.append(event)
            if event == "DONATION":
                if failure == "network":
                    raise httpx.ConnectError("offline", request=request)
                return httpx.Response(failure)
            await emit(session.socket_client, "SYSTEM", system("subscribed", event))
            return httpx.Response(200)
        async with httpx.AsyncClient(base_url="https://example.test", transport=httpx.MockTransport(respond)) as http:
            monkeypatch.setattr(chat, "_client", http)
            assert await session.subscribe_events() == {"CHAT": True, "DONATION": False, "SUBSCRIPTION": True}
            await session.subscribe_events()
        assert session.socket_client.subscribed_events == {"CHAT", "SUBSCRIPTION"}
        assert requests.count("DONATION") == (1 if failure == 403 else 2)
    asyncio.run(run())


def test_401_refreshes_token_and_retries_same_event(monkeypatch):
    async def run():
        session = make_session()
        tokens = []
        async def refresh():
            session.access_token = "renewed"
            return True
        session._refresh_token = AsyncMock(side_effect=refresh)
        async def respond(request):
            tokens.append(request.headers["Authorization"])
            if len(tokens) == 1:
                return httpx.Response(401)
            await emit(session.socket_client, "SYSTEM", system("subscribed", "DONATION"))
            return httpx.Response(200)
        async with httpx.AsyncClient(base_url="https://example.test", transport=httpx.MockTransport(respond)) as http:
            monkeypatch.setattr(chat, "_client", http)
            assert await session.subscribe_donation()
        assert tokens == ["Bearer test-access-token", "Bearer renewed"]
        session._refresh_token.assert_awaited_once()
    asyncio.run(run())


def test_http_success_without_system_confirmation_is_not_subscribed(monkeypatch):
    async def run():
        session = make_session()
        wait = session.socket_client.wait_for_subscription
        session.socket_client.wait_for_subscription = lambda event: wait(event, timeout=0.001)
        async with httpx.AsyncClient(base_url="https://example.test", transport=httpx.MockTransport(
            lambda request: httpx.Response(200))) as http:
            monkeypatch.setattr(chat, "_client", http)
            assert not await session.subscribe_donation()
        assert "DONATION" not in session.socket_client.subscribed_events
    asyncio.run(run())


def test_delayed_confirmation_and_concurrent_restore_do_not_duplicate_requests(monkeypatch):
    async def run():
        session = make_session()
        requests, confirmations = [], []
        async def confirm(event):
            await asyncio.sleep(0.001)
            await emit(session.socket_client, "SYSTEM", system("subscribed", event))
        async def respond(request):
            event = request.url.path.rsplit("/", 1)[1].upper()
            requests.append(event)
            confirmations.append(asyncio.create_task(confirm(event)))
            return httpx.Response(200)
        async with httpx.AsyncClient(base_url="https://example.test", transport=httpx.MockTransport(respond)) as http:
            monkeypatch.setattr(chat, "_client", http)
            results = await asyncio.gather(session.subscribe_events(), session.subscribe_events())
            await asyncio.gather(*confirmations)
        assert results == [dict.fromkeys(chat_client.EVENT_TYPES, True)] * 2
        assert requests == list(chat_client.EVENT_TYPES)
    asyncio.run(run())


def test_revoked_event_is_not_retried_but_cancelled_event_is_recovered(monkeypatch):
    async def run():
        session = make_session()
        client = session.socket_client
        for event in chat_client.EVENT_TYPES:
            await emit(client, "SYSTEM", system("subscribed", event))
        await emit(client, "SYSTEM", system("revoked", "DONATION"))
        await emit(client, "SYSTEM", system("unsubscribed", "SUBSCRIPTION"))
        requested = []
        async def respond(request):
            event = request.url.path.rsplit("/", 1)[1].upper()
            requested.append(event)
            await emit(client, "SYSTEM", system("subscribed", event))
            return httpx.Response(200)
        async with httpx.AsyncClient(base_url="https://example.test", transport=httpx.MockTransport(respond)) as http:
            monkeypatch.setattr(chat, "_client", http)
            assert await session.subscribe_events() == {"CHAT": True, "DONATION": False, "SUBSCRIPTION": True}
        assert requested == ["SUBSCRIPTION"]
    asyncio.run(run())


def test_response_for_old_session_key_is_not_treated_as_success(monkeypatch):
    async def run():
        session = make_session()
        async def respond(request):
            session.session_key = "new-key"
            session.socket_client.session_key = "new-key"
            return httpx.Response(200)
        async with httpx.AsyncClient(base_url="https://example.test", transport=httpx.MockTransport(respond)) as http:
            monkeypatch.setattr(chat, "_client", http)
            assert not await session.subscribe_donation()
        assert not session.socket_client.subscribed_events
    asyncio.run(run())


def test_reconnect_resubscribes_all_events_with_new_key(monkeypatch):
    async def run():
        session = make_session()
        keys = []
        async def respond(request):
            keys.append(request.url.params["sessionKey"])
            await emit(session.socket_client, "SYSTEM", system("subscribed", request.url.path.rsplit("/", 1)[1].upper()))
            return httpx.Response(200)
        async with httpx.AsyncClient(base_url="https://example.test", transport=httpx.MockTransport(respond)) as http:
            monkeypatch.setattr(chat, "_client", http)
            await session.subscribe_events()
            await emit(session.socket_client, "SYSTEM", {"type": "connected", "data": {"sessionKey": "new-key"}})
        assert keys == ["session-key"] * 3 + ["new-key"] * 3
        assert session.session_key == "new-key"
        assert session.socket_client.subscribed_events == set(chat_client.EVENT_TYPES)
    asyncio.run(run())


def test_local_socketio_connection_receives_chat_before_and_after_reconnect(monkeypatch):
    async def run():
        sio = socketio.AsyncServer(async_mode="aiohttp")
        server = web.Application()
        sio.attach(server)
        requested = []

        # 고정된 Socket.IO 4.x 테스트 서버의 emit은 최신 Python에서 coroutine을
        # asyncio.wait에 직접 넘기므로, 단일 수신자용 패킷 전송 함수를 사용한다.
        @sio.event
        async def connect(sid, environ):
            await sio._emit_internal(sid, "SYSTEM", json.dumps({"type": "connected", "data": {"sessionKey": sid}}), namespace="/")

        async def subscribe(request):
            sid, event = request.query["sessionKey"], request.match_info["event"].upper()
            assert request.headers["Authorization"] == "Bearer test-access-token"
            requested.append((sid, event))
            await sio._emit_internal(sid, "SYSTEM", json.dumps(system("subscribed", event)), namespace="/")
            return web.json_response({})

        server.router.add_post("/open/v1/sessions/events/subscribe/{event}", subscribe)
        runner = web.AppRunner(server)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        url = f"http://127.0.0.1:{port}"
        session = chat.ChzzkSessions("channel")
        session.access_token, session.channel_name = "test-access-token", "name"
        async def socket_url():
            session.socket_url = url
        session.create_socket_url = AsyncMock(side_effect=socket_url)
        manager = session_manager.SessionManager()
        monkeypatch.setattr(session_manager, "ChzzkSessions", lambda channel: session)
        received = asyncio.Event()
        message = AsyncMock(side_effect=lambda *args, **kwargs: received.set())
        monkeypatch.setattr(chat_client.handler, "on_message", message)
        payload = {"channelId": "channel", "senderChannelId": "viewer", "content": "!명령어",
                   "profile": {"nickname": "시청자"}, "userRoleCode": "common_user"}
        try:
            async with httpx.AsyncClient(base_url=url) as http:
                monkeypatch.setattr(chat, "_client", http)
                await manager.get_or_create_session("channel")
                first_key = session.session_key
                await sio._emit_internal(first_key, "CHAT", json.dumps(payload), namespace="/")
                await asyncio.wait_for(received.wait(), 2)
                received.clear()
                # 명시적 disconnect 대신 전송 연결을 끊어 내장 자동 재연결 경로를 검증한다.
                await session.socket_client.socketio.eio.ws.close()
                async def wait_subscribed():
                    while session.session_key == first_key or session.socket_client.subscribed_events != set(chat_client.EVENT_TYPES):
                        await asyncio.sleep(0.01)
                await asyncio.wait_for(wait_subscribed(), 5)
                assert session.session_key != first_key
                await sio._emit_internal(session.session_key, "CHAT", json.dumps(payload), namespace="/")
                await asyncio.wait_for(received.wait(), 2)
                assert requested == [(first_key, event) for event in chat_client.EVENT_TYPES] + [
                    (session.session_key, event) for event in chat_client.EVENT_TYPES]
                assert message.await_count == 2
        finally:
            if session.socket_client:
                await session.socket_client.disconnect()
            await runner.cleanup()
    asyncio.run(run())


@pytest.mark.parametrize("chat_ok", [True, False])
@pytest.mark.parametrize("force_recreate", [False, True])
def test_manager_keeps_chat_when_optional_permissions_are_missing(monkeypatch, chat_ok, force_recreate):
    session = NS(create_session=AsyncMock(), session_key="key", socket_url="url",
                 socket_client=NS(disconnect=AsyncMock()),
                 subscribe_chat=AsyncMock(return_value=chat_ok),
                 subscribe_events=AsyncMock(return_value={"CHAT": chat_ok, "DONATION": False, "SUBSCRIPTION": False}))
    monkeypatch.setattr(session_manager, "ChzzkSessions", lambda channel: session)
    manager = session_manager.SessionManager()
    old_session = NS(socket_client=NS(disconnect=AsyncMock()))
    if force_recreate:
        manager.add_session("channel", old_session)
    if chat_ok:
        assert asyncio.run(manager.get_or_create_session("channel", force_recreate=force_recreate)) == (session, True)
        session.socket_client.disconnect.assert_not_awaited()
        if force_recreate:
            old_session.socket_client.disconnect.assert_awaited_once()
    else:
        with pytest.raises(Exception, match="채팅 구독"):
            asyncio.run(manager.get_or_create_session("channel", force_recreate=force_recreate))
        assert manager.active_sessions == ({"channel": old_session} if force_recreate else {})
        old_session.socket_client.disconnect.assert_not_awaited()
        session.socket_client.disconnect.assert_awaited_once()


@pytest.mark.parametrize("connected", [True, False])
def test_watchdog_repairs_subscriptions_or_recreates_disconnected_session(monkeypatch, connected):
    session = NS(socket_client=NS(socketio=NS(connected=connected)), subscribe_events=AsyncMock())
    manager = NS(active_sessions={"channel": session}, get_or_create_session=AsyncMock())
    monkeypatch.setattr(session_watchdog, "session_manager", manager)
    asyncio.run(session_watchdog.SessionWatchdog().check_once())
    if connected:
        session.subscribe_events.assert_awaited_once()
        manager.get_or_create_session.assert_not_awaited()
    else:
        manager.get_or_create_session.assert_awaited_once_with("channel", force_recreate=True)
