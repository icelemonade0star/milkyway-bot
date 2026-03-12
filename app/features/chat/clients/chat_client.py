import socketio
import json
import asyncio

import app.core.config as config
from .base import BaseChatClient
from app.features.chat.handling import handler
from app.core.logger import get_channel_logger

class ChzzkChatClient(BaseChatClient):

    def __init__(self, channel_name, session_key_future: asyncio.Future = None):
        # 각 인스턴스마다 고유한 식별자와 소켓 클라이언트를 가짐
        self.channel_name = channel_name  
        self.socketio = socketio.AsyncClient(
            request_timeout=10,
            reconnection=True,      # 자동 재연결 활성화
            reconnection_attempts=5 # 재연결 시도 횟수
            )
        self.session_key = None
        self.session_key_future = session_key_future

        # 중앙화된 로거 사용
        self.logger = get_channel_logger(self.channel_name)

        # 이벤트 핸들러 등록
        self._setup_handlers()

    def _setup_handlers(self):
        @self.socketio.event
        async def connect():
            self.logger.info("서버에 연결되었습니다.")

        @self.socketio.on('SYSTEM')
        async def on_system(data):
            # 로그 출력 시 식별자를 포함하여 구분
            self.logger.info(f"📡 SYSTEM 이벤트 수신")
            self.logger.debug(f"SYSTEM 이벤트 원본 수신: {data}")
            raw_data = json.loads(data)
            
            event_type = raw_data.get("type")
            event_data = raw_data.get("data", {})
            
            if event_type == "connected":
                self.session_key = event_data.get("sessionKey")
                self.logger.info(f"🔑 세션 키 저장: {self.session_key}")
                
                # 세션 키를 기다리는 Future가 있다면 결과 설정 (Polling 제거)
                if self.session_key_future and not self.session_key_future.done():
                    self.session_key_future.set_result(self.session_key)

        @self.socketio.on('CHAT')
        async def on_chat(data):
            raw_data = json.loads(data)
            channel_id = raw_data.get('channelId')
            nickname = raw_data.get('profile', {}).get('nickname')
            user_id = raw_data.get('senderChannelId')
            
            # 봇 자신 및 설정된 다른 봇들의 메시지는 무시
            if nickname in config.BOT_NICKNAMES:
                return

            message = raw_data.get('content')
            role = raw_data.get('profile', {}).get('userRoleCode')
            # 어느 세션에서 발생한 채팅인지 식별자와 함께 출력
            self.logger.info(f"💬{role} : [{nickname}] {message}")

            # 핸들러로 메시지 전달
            await handler.on_message(channel_id, message, role, user_id=user_id, user_name=nickname)

    def get_session_key(self):
        return self.session_key

    async def connect(self, url):
        await self.socketio.connect(url, transports=['websocket'])
        self.logger.info(f"연결 성공: {url}")

    async def disconnect(self):
        await self.socketio.disconnect()
        self.logger.info("연결이 종료되었습니다.")