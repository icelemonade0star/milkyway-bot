import asyncio
import logging

import app.core.config as config
from app.features.chat.session_manager import session_manager

logger = logging.getLogger("SessionWatchdog")


class SessionWatchdog:
    """연결이 끊긴 세션을 재생성하고, 연결된 세션의 누락된 이벤트 구독을 복구합니다.
    """

    def __init__(self, *, interval_seconds: int = config.SESSION_WATCHDOG_INTERVAL_SECONDS):
        self.interval_seconds = max(60, interval_seconds)
        self._stopped = asyncio.Event()

    async def run(self):
        logger.info("세션 워치독 시작: interval=%ss", self.interval_seconds)
        while not self._stopped.is_set():
            try:
                await self.check_once()
            except Exception as e:
                logger.warning("세션 워치독 점검 사이클 실패: %s", e)

            try:
                await asyncio.wait_for(self._stopped.wait(), timeout=self.interval_seconds)
            except asyncio.TimeoutError:
                pass

        logger.info("세션 워치독 중지됨")

    def stop(self):
        self._stopped.set()

    async def check_once(self):
        for channel_id, session in list(session_manager.active_sessions.items()):
            socket_client = session.socket_client
            connected = bool(socket_client and socket_client.socketio.connected)
            if connected:
                try:
                    await session.subscribe_events()
                except Exception as e:
                    logger.warning("[%s] 이벤트 구독 복구 실패: %s", channel_id, e)
                continue

            logger.warning("⚠️ [%s] 세션 연결 끊김 감지. 자동 재생성 시도", channel_id)
            try:
                await session_manager.get_or_create_session(channel_id, force_recreate=True)
                logger.info("✅ [%s] 세션 자동 재생성 완료", channel_id)
            except Exception as e:
                logger.error("❌ [%s] 세션 자동 재생성 실패: %s", channel_id, e)
