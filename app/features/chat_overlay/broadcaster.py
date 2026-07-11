import logging
from dataclasses import dataclass, field

from fastapi import WebSocket

logger = logging.getLogger("ChatOverlayBroadcaster")


@dataclass
class OverlayConnection:
    websocket: WebSocket
    blocked_nicknames: set[str] = field(default_factory=set)
    blocked_roles: set[str] = field(default_factory=set)

    def should_skip(self, payload: dict) -> bool:
        nickname = str(payload.get("nickname") or "").strip().casefold()
        role = str(payload.get("role") or "").strip().casefold()
        return bool(
            nickname and nickname in self.blocked_nicknames
            or role and role in self.blocked_roles
        )


class ChatOverlayBroadcaster:
    def __init__(self):
        self._connections: dict[str, dict[WebSocket, OverlayConnection]] = {}

    async def connect(
        self,
        channel_id: str,
        websocket: WebSocket,
        *,
        blocked_nicknames: list[str] | None = None,
        blocked_roles: list[str] | None = None,
    ):
        await websocket.accept()
        self._connections.setdefault(channel_id, {})[websocket] = OverlayConnection(
            websocket=websocket,
            blocked_nicknames={value.strip().casefold() for value in blocked_nicknames or [] if value.strip()},
            blocked_roles={value.strip().casefold() for value in blocked_roles or [] if value.strip()},
        )

    def disconnect(self, channel_id: str, websocket: WebSocket):
        connections = self._connections.get(channel_id)
        if not connections:
            return
        connections.pop(websocket, None)
        if not connections:
            self._connections.pop(channel_id, None)

    def has_connections(self, channel_id: str) -> bool:
        return bool(self._connections.get(channel_id))

    async def publish(self, channel_id: str, payload: dict):
        connections = list(self._connections.get(channel_id, {}).values())
        if not connections:
            return

        stale: list[WebSocket] = []
        for connection in connections:
            if connection.should_skip(payload):
                continue
            try:
                await connection.websocket.send_json(payload)
            except Exception as exc:
                logger.debug("오버레이 웹소켓 전송 실패: %s", exc)
                stale.append(connection.websocket)

        for websocket in stale:
            self.disconnect(channel_id, websocket)


chat_overlay_broadcaster = ChatOverlayBroadcaster()
timer_overlay_broadcaster = ChatOverlayBroadcaster()
