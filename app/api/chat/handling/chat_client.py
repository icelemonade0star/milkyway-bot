import socketio
import json
import asyncio
import logging

from pathlib import Path

class ChzzkChatClient:
    def __init__(self, channel_name):
        # 각 인스턴스마다 고유한 식별자와 소켓 클라이언트를 가짐
        self.channel_name = channel_name  
        self.socketio = socketio.AsyncClient(
            request_timeout=10,
            reconnection=True,      # 자동 재연결 활성화
            reconnection_attempts=5 # 재연결 시도 횟수
            )
        self.session_key = None

        self.logger = logging.getLogger(f"Chzzk.{self.channel_name}")
        self.logger.setLevel(logging.DEBUG)

        log_dir = Path.cwd() / "logs" / self.channel_name  # 프로젝트 루트/logs/channel_name
        log_dir.mkdir(parents=True, exist_ok=True) # 폴더가 없으면 생성
        log_file = log_dir / "chat_client.log"
        
        # 3. 핸들러 중복 등록 방지 (인스턴스 재생성 시 대비)
        if not self.logger.handlers:
            # 파일 핸들러 (UTF-8 설정 권장)
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setLevel(logging.DEBUG)
            
            # 콘솔 핸들러 (선택 사항: print 대신 로그로 통일하고 싶을 때)
            stream_handler = logging.StreamHandler()
            stream_handler.setLevel(logging.INFO)
            
            formatter = logging.Formatter('%(asctime)s - [%(name)s] - %(levelname)s - %(message)s')
            file_handler.setFormatter(formatter)
            stream_handler.setFormatter(formatter)
            
            self.logger.addHandler(file_handler)
            self.logger.addHandler(stream_handler)

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

        @self.socketio.on('CHAT')
        async def on_chat(data):
            raw_data = json.loads(data)
            nickname = raw_data.get('profile', {}).get('nickname')
            message = raw_data.get('content')
            # 어느 세션에서 발생한 채팅인지 식별자와 함께 출력
            self.logger.info(f"💬 [{nickname}] {message}")


    def get_session_key(self):
        return self.session_key

    async def connect(self, url):
        try:
            await self.socketio.connect(url, transports=['websocket'])
            self.logger.info(f"연결 시도 중: {url}")
        except Exception as e:
            self.logger.error(f"연결 실패: {e}")

    async def disconnect(self):
        await self.socketio.disconnect()
        self.logger.info("연결이 종료되었습니다.")

# --- 실행 예시 ---
async def main():
    # 여러 명의 유저 세션을 동시에 관리
    user_a = ChzzkChatClient(channel_name="User_A")
    user_b = ChzzkChatClient(channel_name="User_B")

    await asyncio.gather(
        user_a.connect("치지직_소켓_URL"),
        user_b.connect("치지직_소켓_URL")
    )

    # 계속 유지...