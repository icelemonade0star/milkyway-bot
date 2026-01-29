import socketio
import time
from typing import Optional

from app.chzzk.api_client import ChzzkAPIClient

class ChzzkChatListener:
    def __init__(self, api_client: ChzzkAPIClient):
        self.api_client = api_client
        self.sio = socketio.Client(reconnection=True)
        self.session_key: Optional[str] = None
        self.channel_id: Optional[str] = None
        self._setup_handlers()

    def _setup_handlers(self):
        @self.sio.event
        def connect():
            print("✅ Connected to CHZZK session server")

        @self.sio.on("message")
        def on_message(data):
            if not isinstance(data, dict):
                print("Unknown message:", data)
                return

            event_type = data.get("eventType") or data.get("type")

            if event_type == "connected":
                self.session_key = data["data"]["sessionKey"]
                print(f"✅ SessionKey received: {self.session_key}")
                if self.channel_id:  # 채널 구독 즉시 실행
                    self.api_client.subscribe_chat(self.session_key, self.channel_id)

            elif event_type == "CHAT":
                print(f"💬 [{data.get('channelId')}] {data.get('senderNickname')}: {data.get('content')}")

            elif event_type == "SYSTEM" or event_type in ("subscribed", "unsubscribed"):
                print(f"📡 System: {data}")
            else:
                print(f"📨 Other: {data}")

        @self.sio.event
        def disconnect():
            print("❌ Disconnected from CHZZK")

    def start(self, channel_id: str):
        self.channel_id = channel_id
        
        # 세션 URL 생성 후 연결
        socket_url = self.api_client.create_session_url()
        print(f"🔗 Connecting to: {socket_url}")
        
        self.sio.connect(socket_url, transports=["websocket"])
        
        try:
            self.sio.wait()  # 블로킹 대기
        except KeyboardInterrupt:
            print("🛑 Stopping...")
            self.sio.disconnect()