import socketio
import json
import asyncio
import logging

import app.core.config as config
from .base import BaseChatClient
from app.features.chat.handling import message_handling

from pathlib import Path

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

        self.logger = logging.getLogger(f"Chzzk.{self.channel_name}")
        self.logger.setLevel(logging.DEBUG)
        # 부모 로거(Root)로 전파 차단 -> Docker(콘솔) 로그에 출력되지 않게 함
        self.logger.propagate = False

        log_dir = Path.cwd() / "logs" / self.channel_name  # 프로젝트 루트/logs/channel_name
        log_dir.mkdir(parents=True, exist_ok=True) # 폴더가 없으면 생성
        log_file = log_dir / "chat_client.log"
        
        # 3. 핸들러 중복 등록 방지 (인스턴스 재생성 시 대비)
        if not self.logger.handlers:
            # 파일 핸들러 (UTF-8 설정 권장)
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setLevel(logging.DEBUG)
            
            formatter = logging.Formatter('%(asctime)s - [%(name)s] - %(levelname)s - %(message)s')
            file_handler.setFormatter(formatter)
            
            self.logger.addHandler(file_handler)

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
            await message_handling.on_message(channel_id, message, role, user_id=user_id, user_name=nickname)

    def get_session_key(self):
        return self.session_key

    async def connect(self, url):
        await self.socketio.connect(url, transports=['websocket'])
        self.logger.info(f"연결 성공: {url}")

    async def disconnect(self):
        await self.socketio.disconnect()
        self.logger.info("연결이 종료되었습니다.")