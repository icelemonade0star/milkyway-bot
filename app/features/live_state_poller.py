import asyncio
import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select

import app.core.config as config
from app.db import models
from app.platforms.registry import get_live_provider
from app.redis.redis_service import redis_client

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
            "Live state poller started: interval=%ss concurrency=%s",
            self.interval_seconds,
            self.concurrency,
        )
        while not self._stopped.is_set():
            try:
                await self.poll_once()
            except Exception as e:
                logger.warning("Live state poll cycle failed: %s", e)

            try:
                await asyncio.wait_for(self._stopped.wait(), timeout=self.interval_seconds)
            except asyncio.TimeoutError:
                pass

        logger.info("Live state poller stopped")

    def stop(self):
        self._stopped.set()

    async def poll_once(self):
        async with self.session_factory() as db:
            channels = (await db.execute(
                select(models.V2Channel).where(models.V2Channel.is_active == True)
            )).scalars().all()

        if not channels:
            return

        sem = asyncio.Semaphore(self.concurrency)

        async def bounded(channel):
            async with sem:
                await self._poll_channel(channel)

        results = await asyncio.gather(*(bounded(channel) for channel in channels), return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                logger.warning("Live state poll task failed: %s", result)

    async def _poll_channel(self, channel: models.V2Channel):
        try:
            provider = get_live_provider(channel.platform)
        except ValueError:
            logger.debug("No live provider for platform=%s", channel.platform)
            return

        try:
            live_status = await provider.get_live_status(channel.platform_channel_id)
        except Exception as e:
            logger.warning(
                "Live status lookup failed: platform=%s channel=%s error=%s",
                channel.platform,
                channel.platform_channel_id,
                e,
            )
            return

        async with self.session_factory() as db:
            db_channel = await db.get(models.V2Channel, channel.id)
            if not db_channel or not db_channel.is_active:
                return

            if not live_status:
                return

            if live_status.status == "OPEN" and live_status.opened_at:
                await self._mark_open(db, db_channel, live_status)
                await self._cache_live_status(db_channel.platform_channel_id, live_status.raw or {}, is_open=True)
            elif live_status.status == "CLOSE":
                await self._mark_closed(db, db_channel, live_status.raw or {})
                await self._cache_live_status(db_channel.platform_channel_id, "CLOSE", is_open=False)
            else:
                await self._mark_unknown(db, db_channel, live_status.raw)

            await db.commit()

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
        if not live_state:
            live_state = models.V2ChannelLiveState(channel_id=channel.id)
            db.add(live_state)
        live_state.status = "OPEN"
        live_state.current_stream_session_id = existing.id
        live_state.last_checked_at = datetime.now(timezone.utc)
        live_state.raw_status = live_status.raw or {}

        if channel.platform == "chzzk":
            legacy_open_sessions = (await db.execute(
                select(models.StreamSession).where(
                    models.StreamSession.chzzk_channel_id == channel.platform_channel_id,
                    models.StreamSession.closed_at.is_(None),
                    models.StreamSession.opened_at != live_status.opened_at,
                )
            )).scalars().all()
            for session in legacy_open_sessions:
                session.closed_at = datetime.now(timezone.utc)

            legacy = (await db.execute(
                select(models.StreamSession).where(
                    models.StreamSession.chzzk_channel_id == channel.platform_channel_id,
                    models.StreamSession.opened_at == live_status.opened_at,
                )
            )).scalar_one_or_none()
            if not legacy:
                db.add(models.StreamSession(
                    chzzk_channel_id=channel.platform_channel_id,
                    opened_at=live_status.opened_at,
                    stream_title=live_status.title,
                ))
            else:
                legacy.closed_at = None
                legacy.stream_title = live_status.title

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

        if channel.platform == "chzzk":
            latest = (await db.execute(
                select(models.StreamSession)
                .where(
                    models.StreamSession.chzzk_channel_id == channel.platform_channel_id,
                    models.StreamSession.closed_at.is_(None),
                )
                .order_by(models.StreamSession.opened_at.desc())
                .limit(1)
            )).scalar_one_or_none()
            if latest:
                latest.closed_at = now

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

    async def _cache_live_status(self, platform_channel_id: str, value, *, is_open: bool):
        cache_key = f"live_status:{platform_channel_id}"
        try:
            if is_open:
                await redis_client.set(cache_key, json.dumps(value), ex=300)
            else:
                await redis_client.set(cache_key, value, ex=60)
        except Exception as e:
            logger.warning("Live status cache update failed: %s", e)
