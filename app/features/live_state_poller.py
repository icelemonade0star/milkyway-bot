import asyncio
import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select

import app.core.config as config
from app.db import models
from app.platforms.registry import get_live_provider
from app.redis.redis_service import RedisChannelKey, RedisConfigService, redis_client

logger = logging.getLogger("LiveStatePoller")


class LiveStatePoller:
    def __init__(
        self,
        session_factory,
        *,
        interval_seconds: int = config.LIVE_STATE_POLL_INTERVAL_SECONDS,
        concurrency: int = config.LIVE_STATE_POLL_CONCURRENCY,
    ):
        self.session_factory = session_factory
        self.interval_seconds = max(10, interval_seconds)
        self.concurrency = max(1, concurrency)
        self._stopped = asyncio.Event()

    async def run(self):
        logger.info(
            "라이브 상태 폴러 시작: interval=%ss concurrency=%s",
            self.interval_seconds,
            self.concurrency,
        )
        while not self._stopped.is_set():
            try:
                await self.poll_once()
            except Exception as e:
                logger.warning("라이브 상태 폴링 사이클 실패: %s", e)

            try:
                await asyncio.wait_for(self._stopped.wait(), timeout=self.interval_seconds)
            except asyncio.TimeoutError:
                pass

        logger.info("라이브 상태 폴러 중지됨")

    def stop(self):
        self._stopped.set()

    async def poll_once(self):
        async with self.session_factory() as db:
            channels = (await db.execute(
                select(models.V2Channel).where(models.V2Channel.is_active == True)
            )).scalars().all()

        if not channels:
            return 0

        sem = asyncio.Semaphore(self.concurrency)

        async def bounded(channel):
            async with sem:
                return await self._poll_channel(channel)

        results = await asyncio.gather(*(bounded(channel) for channel in channels), return_exceptions=True)
        refreshed_count = 0
        for result in results:
            if isinstance(result, Exception):
                logger.warning("라이브 상태 폴링 태스크 실패: %s", result)
            elif result:
                refreshed_count += 1
        return refreshed_count

    async def poll_channel_by_platform_id(self, platform: str, platform_channel_id: str) -> bool:
        async with self.session_factory() as db:
            channel = (await db.execute(
                select(models.V2Channel).where(
                    models.V2Channel.platform == platform,
                    models.V2Channel.platform_channel_id == platform_channel_id,
                )
            )).scalar_one_or_none()

        if not channel:
            return False

        return await self._poll_channel(channel)

    async def _poll_channel(self, channel: models.V2Channel):
        try:
            provider = get_live_provider(channel.platform)
        except ValueError:
            logger.debug("플랫폼에 대한 라이브 프로바이더 없음: platform=%s", channel.platform)
            return False

        try:
            live_status = await provider.get_live_status(channel.platform_channel_id)
        except Exception as e:
            logger.warning(
                "라이브 상태 조회 실패: platform=%s channel=%s error=%s",
                channel.platform,
                channel.platform_channel_id,
                e,
            )
            return False

        if not live_status:
            return False

        async with self.session_factory() as db:
            db_channel = await db.get(models.V2Channel, channel.id)
            if not db_channel or not db_channel.is_active:
                return False

            should_notify_discord = False
            if live_status.status == "OPEN" and live_status.opened_at:
                should_notify_discord = await self._mark_open(db, db_channel, live_status)
                await self._cache_live_status(db_channel, live_status, is_open=True)
            elif live_status.status == "CLOSE":
                await self._mark_closed(db, db_channel, live_status.raw or {})
                await self._cache_live_status(db_channel, "CLOSE", is_open=False)
            else:
                await self._mark_unknown(db, db_channel, live_status.raw)

            await db.commit()

            if should_notify_discord:
                try:
                    from app.features.discord_bot.cogs.chzzk_notifications import trigger_live_notification_check

                    await trigger_live_notification_check(db_channel.platform, db_channel.platform_channel_id)
                except Exception as e:
                    logger.warning("Discord 방송 알림 트리거 실패: %s", e)

            return True

    async def _mark_open(self, db, channel: models.V2Channel, live_status):
        existing = (await db.execute(
            select(models.V2StreamSession).where(
                models.V2StreamSession.channel_id == channel.id,
                models.V2StreamSession.opened_at == live_status.opened_at,
            )
        )).scalar_one_or_none()

        if not existing:
            existing = models.V2StreamSession(
                channel_id=channel.id,
                opened_at=live_status.opened_at,
                stream_title=live_status.title,
                category=live_status.category,
                thumbnail_url=live_status.thumbnail_url,
                raw_live_response=live_status.raw or {},
            )
            db.add(existing)
            await db.flush()
        else:
            existing.closed_at = None
            existing.stream_title = live_status.title
            existing.category = live_status.category
            existing.thumbnail_url = live_status.thumbnail_url
            existing.raw_live_response = live_status.raw or {}

        await self._close_other_v2_sessions(db, channel.id, existing.id)

        live_state = await db.get(models.V2ChannelLiveState, channel.id)
        previous_status = live_state.status if live_state else None
        previous_session_id = live_state.current_stream_session_id if live_state else None
        if not live_state:
            live_state = models.V2ChannelLiveState(channel_id=channel.id)
            db.add(live_state)
        live_state.status = "OPEN"
        live_state.current_stream_session_id = existing.id
        live_state.last_checked_at = datetime.now(timezone.utc)
        live_state.raw_status = live_status.raw or {}
        return previous_status != "OPEN" or previous_session_id != existing.id

    async def _mark_closed(self, db, channel: models.V2Channel, raw_status: dict | None):
        now = datetime.now(timezone.utc)

        await self._close_other_v2_sessions(db, channel.id, keep_session_id=None, closed_at=now)

        live_state = await db.get(models.V2ChannelLiveState, channel.id)
        if not live_state:
            live_state = models.V2ChannelLiveState(channel_id=channel.id)
            db.add(live_state)
        live_state.status = "CLOSE"
        live_state.current_stream_session_id = None
        live_state.last_checked_at = now
        live_state.raw_status = raw_status

    async def _mark_unknown(self, db, channel: models.V2Channel, raw_status: dict | None):
        live_state = await db.get(models.V2ChannelLiveState, channel.id)
        if not live_state:
            live_state = models.V2ChannelLiveState(channel_id=channel.id)
            db.add(live_state)
        live_state.status = "UNKNOWN"
        live_state.last_checked_at = datetime.now(timezone.utc)
        live_state.raw_status = raw_status

    async def _close_other_v2_sessions(self, db, channel_id, keep_session_id=None, closed_at=None):
        now = closed_at or datetime.now(timezone.utc)
        stmt = select(models.V2StreamSession).where(
            models.V2StreamSession.channel_id == channel_id,
            models.V2StreamSession.closed_at.is_(None),
        )
        if keep_session_id:
            stmt = stmt.where(models.V2StreamSession.id != keep_session_id)

        sessions = (await db.execute(stmt)).scalars().all()
        for session in sessions:
            session.closed_at = now

    async def _cache_live_status(self, channel: models.V2Channel, value, *, is_open: bool):
        redis_channel = RedisChannelKey(
            channel.platform,
            channel.platform_channel_id,
            str(channel.id),
        )
        cache_key = RedisConfigService.get_live_status_key(redis_channel)
        try:
            if is_open:
                await redis_client.set(cache_key, json.dumps(RedisConfigService.serialize_live_status(value)), ex=300)
            else:
                await redis_client.set(cache_key, value, ex=60)
        except Exception as e:
            logger.warning("방송 상태 캐시 업데이트 실패: %s", e)
