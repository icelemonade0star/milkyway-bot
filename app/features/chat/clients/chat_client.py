import socketio
import json
import asyncio
from collections.abc import Awaitable, Callable

import app.core.config as config
from .base import BaseChatClient
from app.features.chat.handling import handler
from app.features.chat.handling import events
from app.core.logger import get_channel_logger

EVENT_TYPES = ("CHAT", "DONATION", "SUBSCRIPTION")

class ChzzkChatClient(BaseChatClient):

    def __init__(
        self, channel_name, platform_channel_id: str,
        session_key_future: asyncio.Future | None = None,
        on_reconnect: Callable[[str], Awaitable[None]] | None = None,
    ):
        # 각 인스턴스마다 고유한 식별자와 소켓 클라이언트를 가짐
        self.channel_name = channel_name  
        self.platform_channel_id = platform_channel_id
        self.socketio = socketio.AsyncClient(
            request_timeout=10,
            reconnection=True,      # 자동 재연결 활성화
            reconnection_attempts=5 # 재연결 시도 횟수
            )
        self.session_key = None
        self.session_key_future = session_key_future
        self.on_reconnect = on_reconnect
        self.subscribed_events: set[str] = set()
        self.denied_events: set[str] = set()
        self._subscription_signals = {event: asyncio.Event() for event in EVENT_TYPES}

        # 중앙화된 로거 사용
        self.logger = get_channel_logger(self.channel_name)

        # 이벤트 핸들러 등록
        self._setup_handlers()

    def _setup_handlers(self):
        @self.socketio.event
        async def connect():
            self.logger.info("서버에 연결되었습니다.")

        @self.socketio.event
        async def disconnect():
            self._clear_subscriptions()
            self.logger.warning("서버 연결이 끊어졌습니다.")

        async def on_system(data):
            # 로그 출력 시 식별자를 포함하여 구분
            self.logger.info(f"📡 SYSTEM 이벤트 수신")
            self.logger.debug(f"SYSTEM 이벤트 원본 수신: {data}")
            raw_data = self._parse_payload(data, "SYSTEM")
            if raw_data is None:
                return
            
            event_type = raw_data.get("type")
            event_data = raw_data.get("data", {})
            if not isinstance(event_type, str) or not isinstance(event_data, dict):
                return
            
            if event_type == "connected":
                session_key = event_data.get("sessionKey")
                if not isinstance(session_key, str) or not session_key:
                    return
                self.session_key = session_key
                self._clear_subscriptions()
                self.logger.info("세션 키 수신 완료")
                
                # 세션 키를 기다리는 Future가 있다면 결과 설정 (Polling 제거)
                if self.session_key_future and not self.session_key_future.done():
                    self.session_key_future.set_result(self.session_key)
                elif self.on_reconnect:
                    await self.on_reconnect(session_key)
            elif event_type in {"subscribed", "unsubscribed", "revoked"}:
                event = event_data.get("eventType")
                if event not in EVENT_TYPES or event_data.get("channelId") != self.platform_channel_id:
                    return
                if event_type == "subscribed":
                    self.subscribed_events.add(event)
                    self.denied_events.discard(event)
                    self.logger.info("이벤트 구독 확인: eventType=%s", event)
                else:
                    self.subscribed_events.discard(event)
                    if event_type == "revoked":
                        self.denied_events.add(event)
                        self.logger.warning("이벤트 권한 회수: eventType=%s, 권한 확인 및 재인증 필요", event)
                    else:
                        self.logger.warning("이벤트 구독 취소: eventType=%s", event)
                self._subscription_signals[event].set()

        self.socketio.on('SYSTEM', handler=on_system)

        async def on_chat(data):
            raw_data = self._parse_payload(data, "CHAT")
            if raw_data is None:
                return
            channel_id = raw_data.get('channelId') or self.platform_channel_id
            if channel_id != self.platform_channel_id:
                return
            if not isinstance(raw_data.get('profile'), dict) or not isinstance(raw_data.get('content'), str):
                return
            nickname = raw_data.get('profile', {}).get('nickname')
            user_id = raw_data.get('senderChannelId')
            
            # 봇 자신 및 설정된 다른 봇들의 메시지는 무시
            if nickname in config.BOT_NICKNAMES:
                return

            message = raw_data.get('content')
            role = raw_data.get('userRoleCode') or raw_data.get('profile', {}).get('userRoleCode')
            # 어느 세션에서 발생한 채팅인지 식별자와 함께 출력
            self.logger.info(f"💬{role} : [{nickname}] {message}")

            # 핸들러로 메시지 전달
            await handler.on_message(channel_id, message, role, user_id=user_id, user_name=nickname)

        self.socketio.on('CHAT', handler=on_chat)

        async def on_donation(data):
            payload = self._parse_payload(data, "DONATION")
            if payload is not None and payload.get("channelId") == self.platform_channel_id:
                await events.on_donation(self.platform_channel_id, payload)

        async def on_subscription(data):
            payload = self._parse_payload(data, "SUBSCRIPTION")
            if payload is not None and payload.get("channelId") == self.platform_channel_id:
                await events.on_subscription(self.platform_channel_id, payload)

        self.socketio.on('DONATION', handler=on_donation)
        self.socketio.on('SUBSCRIPTION', handler=on_subscription)

    def _parse_payload(self, data, event: str) -> dict | None:
        try:
            payload = json.loads(data) if isinstance(data, (str, bytes)) else data
        except (ValueError, UnicodeDecodeError):
            payload = None
        if not isinstance(payload, dict):
            self.logger.warning("이벤트 데이터 형식 오류: eventType=%s", event)
            return None
        return payload

    def _clear_subscriptions(self):
        self.subscribed_events.clear()
        for signal in self._subscription_signals.values():
            signal.clear()

    def prepare_subscription(self, event: str):
        self._subscription_signals[event].clear()

    async def wait_for_subscription(self, event: str, timeout: float = 5.0) -> bool:
        if event not in self.subscribed_events:
            try:
                await asyncio.wait_for(self._subscription_signals[event].wait(), timeout)
            except asyncio.TimeoutError:
                return False
        return event in self.subscribed_events

    def get_session_key(self):
        return self.session_key

    async def connect(self, url):
        await self.socketio.connect(url, transports=['websocket'])
        self.logger.info(f"연결 성공: {url}")

    async def disconnect(self):
        await self.socketio.disconnect()
        self.logger.info("연결이 종료되었습니다.")
