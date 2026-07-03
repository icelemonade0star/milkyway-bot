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
            self._locks.pop(channel_id, None)

    async def ensure_raw_client(self, channel_id: str) -> None:
        # 빠른 경로: 이미 실행 중이면 락 없이 반환
        existing_task = self._tasks.get(channel_id)
        if existing_task and not existing_task.done():
            return

        self._cleanup_done(channel_id)

        if channel_id not in self._locks:
            self._locks[channel_id] = asyncio.Lock()

        async with self._locks[channel_id]:
            # double-check: 락 대기 중에 다른 코루틴이 이미 생성했을 수 있음
            existing_task = self._tasks.get(channel_id)
            if existing_task and not existing_task.done():
                return

            logger.info("[%s] raw WS 클라이언트 생성", channel_id)
            client = ChzzkRawChatClient(channel_id)
            self._clients[channel_id] = client

            task = asyncio.create_task(client.run_forever(), name=f"raw-ws-{channel_id}")
            self._tasks[channel_id] = task


overlay_manager = OverlayRawClientManager()
