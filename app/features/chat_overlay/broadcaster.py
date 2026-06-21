import logging

from fastapi import WebSocket

logger = logging.getLogger("ChatOverlayBroadcaster")


class ChatOverlayBroadcaster:
    def __init__(self):
        self._connections: dict[str, set[WebSocket]] = {}

    async def connect(self, channel_id: str, websocket: WebSocket):
        await websocket.accept()
        self._connections.setdefault(channel_id, set()).add(websocket)

    def disconnect(self, channel_id: str, websocket: WebSocket):
        connections = self._connections.get(channel_id)
        if not connections:
            return
        connections.discard(websocket)
        if not connections:
            self._connections.pop(channel_id, None)

    async def publish(self, channel_id: str, payload: dict):
        connections = list(self._connections.get(channel_id, ()))
        if not connections:
            return

        stale: list[WebSocket] = []
        for websocket in connections:
            try:
                await websocket.send_json(payload)
            except Exception as exc:
                logger.debug("Overlay websocket send failed: %s", exc)
                stale.append(websocket)

        for websocket in stale:
            self.disconnect(channel_id, websocket)


chat_overlay_broadcaster = ChatOverlayBroadcaster()
