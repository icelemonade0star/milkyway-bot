import asyncio
import logging

from app.core.config import DRAWING_DONATION_CLEANUP_INTERVAL_SECONDS
from app.features.drawing_donation.service import DrawingDonationService, RETENTION_HOURS

logger = logging.getLogger("DrawingDonationCleanup")


class DrawingDonationCleanup:
    def __init__(self, session_factory, *, interval_seconds: float = DRAWING_DONATION_CLEANUP_INTERVAL_SECONDS):
        self.session_factory = session_factory
        self.interval_seconds = max(1, interval_seconds)
        self._stopped = asyncio.Event()

    async def cleanup_once(self) -> int:
        deleted = 0
        # 대량 정리로 DB 연결을 오래 점유하지 않도록 배치마다 세션을 반납한다.
        for _ in range(20):
            if self._stopped.is_set():
                break
            async with self.session_factory() as db:
                count = await DrawingDonationService(db).delete_expired_drawings()
            deleted += count
            if count < 250:
                break
        return deleted

    async def run(self):
        logger.info("그림 데이터 정리 시작: 삭제 기준=%s시간 경과, 정리 주기=%s초", RETENTION_HOURS, self.interval_seconds)
        while not self._stopped.is_set():
            try:
                deleted = await self.cleanup_once()
                if deleted:
                    logger.info("보관 기간이 지난 그림 삭제 완료: %s개", deleted)
            except Exception as exc:
                logger.warning("그림 데이터 정리 실패, 다음 주기에 재시도: %s", exc)
            try:
                await asyncio.wait_for(self._stopped.wait(), timeout=self.interval_seconds)
            except asyncio.TimeoutError:
                pass
        logger.info("그림 데이터 정리 중지됨")

    def stop(self):
        self._stopped.set()
