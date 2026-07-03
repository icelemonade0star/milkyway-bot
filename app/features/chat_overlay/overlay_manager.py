import asyncio
import logging

from app.features.chat_overlay.chzzk_raw_client import ChzzkRawChatClient

logger = logging.getLogger("OverlayManager")


class OverlayRawClientManager:
    def __init__(self):
        self._clients: dict[str, ChzzkRawChatClient] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def _cleanup_done(self, channel_id: str) -> None:
        task = self._tasks.get(channel_id)
        if task and task.done():
            self._tasks.pop(channel_id, None)
            self._clients.pop(channel_id, None)

    async def ensure_raw_client(self, channel_id: str) -> None:
        lock = self._locks.setdefault(channel_id, asyncio.Lock())
        async with lock:
            self._cleanup_done(channel_id)
            existing_task = self._tasks.get(channel_id)
            if existing_task and not existing_task.done():
                return

            logger.info("[%s] raw WS 클라이언트 생성", channel_id)
            client = ChzzkRawChatClient(channel_id)
            self._clients[channel_id] = client

            task = asyncio.create_task(client.run_forever(), name=f"raw-ws-{channel_id}")
            self._tasks[channel_id] = task

    async def ensure_raw_client_if_connected(self, channel_id: str) -> None:
        from app.features.chat_overlay.broadcaster import chat_overlay_broadcaster

        if chat_overlay_broadcaster.has_connections(channel_id):
            await self.ensure_raw_client(channel_id)

    async def stop_raw_client(self, channel_id: str) -> None:
        lock = self._locks.setdefault(channel_id, asyncio.Lock())
        async with lock:
            task = self._tasks.pop(channel_id, None)
            self._clients.pop(channel_id, None)
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                logger.info("[%s] 방송 종료로 오버레이 raw WS 클라이언트 종료", channel_id)


overlay_manager = OverlayRawClientManager()
