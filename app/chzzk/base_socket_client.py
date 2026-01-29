import socketio
from typing import Dict, Callable, Any, Optional
from abc import ABC, abstractmethod

class BaseSocketEventHandler(ABC):
    """이벤트 핸들러 인터페이스"""
    @abstractmethod
    async def handle_event(self, event_type: str, data: dict) -> None:
        pass

class BaseSocketClient:
    def __init__(self, api_client):
        self.api_client = api_client
        self.sio = socketio.Client(reconnection=True)
        self.handlers: Dict[str, BaseSocketEventHandler] = {}
        self.session_key: Optional[str] = None
        self._register_common_events()

    def register_handler(self, event_type: str, handler: BaseSocketEventHandler):
        """이벤트 타입별 핸들러 등록"""
        self.handlers[event_type] = handler

    def _register_common_events(self):
        @self.sio.event
        def connect():
            print("✅ Connected to CHZZK")

        @self.sio.on("message")
        def on_message(data):
            self._dispatch_message(data)

        @self.sio.event
        def disconnect():
            print("❌ Disconnected")

    def _dispatch_message(self, data):
        """단일 진입점: 이벤트 타입에 따라 핸들러 분배"""
        if not isinstance(data, dict):
            print("Unknown message:", data)
            return

        event_type = data.get("eventType") or data.get("type")
        
        # 시스템 이벤트 처리
        if event_type == "connected":
            self.session_key = data["data"]["sessionKey"]
            print(f"✅ SessionKey: {self.session_key}")
            return

        # 사용자 정의 핸들러 호출
        handler = self.handlers.get(event_type)
        if handler:
            handler.handle_event(event_type, data)
        else:
            print(f"📨 Unhandled: {event_type} - {data}")

    def start(self, channel_id: str):
        socket_url = self.api_client.create_session_url()
        self.sio.connect(socket_url, transports=["websocket"])
        self.api_client.subscribe_chat(self.session_key, channel_id)
        self.sio.wait()