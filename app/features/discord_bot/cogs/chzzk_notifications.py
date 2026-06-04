import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

import discord
from discord.ext import commands, tasks
from sqlalchemy import and_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.database import get_session_factory
from app.db import models
from app.platforms.registry import get_live_provider

_CACHE_TTL = 300.0
_OPEN_POLL_INTERVAL = 300.0

_active_cog: Optional["LiveNotification"] = None


def invalidate_notification_cache():
    if _active_cog is not None:
        _active_cog._cache_loaded_at = 0.0


async def trigger_live_notification_check(platform: str, platform_channel_id: str):
    if _active_cog is not None:
        await _active_cog.trigger_live_notification_check(platform, platform_channel_id)


@dataclass
class LiveNotificationData:
    platform: str
    platform_channel_id: str
    streamer_name: str
    live_title: str
    category: str
    tags: List[str]
    live_url: str
    thumbnail_url: Optional[str] = None
    channel_image_url: Optional[str] = None
    open_date: Optional[str] = None


@dataclass
class _CachedNotification:
    platform: str
    platform_channel_id: str
    discord_channel_id: str
    streamer_name: str
    mention_role: Optional[str]
    last_status: str
    notification_id: Optional[int] = None
    v2_channel_id: Optional[object] = None
    current_stream_session_id: Optional[object] = field(default=None, repr=False)
    _consecutive_close_count: int = field(default=0, repr=False)
    _last_polled_at: float = field(default=0.0, repr=False)

    @property
    def is_v2(self) -> bool:
        return self.notification_id is not None and self.v2_channel_id is not None


class LiveNotification(commands.Cog):
    def __init__(self, bot):
        global _active_cog
        self.bot = bot
        self._cache: dict[str, _CachedNotification] = {}
        self._cache_loaded_at: float = 0.0
        _active_cog = self
        self.check_live_notifications.start()

    def cog_unload(self):
        global _active_cog
        self.check_live_notifications.cancel()
        _active_cog = None

    async def _load_cache(self):
        factory = get_session_factory()
        if not factory:
            return

        try:
            async with factory() as db:
                new_cache: dict[str, _CachedNotification] = {}

                v2_stmt = (
                    select(
                        models.V2LiveNotification,
                        models.V2Channel,
                        models.V2ChannelLiveState,
                        models.V2LiveNotificationDelivery.id,
                    )
                    .join(models.V2Channel, models.V2LiveNotification.channel_id == models.V2Channel.id)
                    .outerjoin(models.V2ChannelLiveState, models.V2ChannelLiveState.channel_id == models.V2Channel.id)
                    .outerjoin(
                        models.V2LiveNotificationDelivery,
                        and_(
                            models.V2LiveNotificationDelivery.notification_id == models.V2LiveNotification.id,
                            models.V2LiveNotificationDelivery.stream_session_id == models.V2ChannelLiveState.current_stream_session_id,
                        ),
                    )
                    .where(
                        models.V2LiveNotification.is_active == True,
                        models.V2LiveNotification.destination_platform == "discord",
                        models.V2Channel.is_active == True,
                    )
                )
                for notification, channel, live_state, delivery_id in (await db.execute(v2_stmt)).all():
                    key = f"v2:{notification.id}"
                    last_status = (
                        "OPEN"
                        if live_state and live_state.status == "OPEN" and delivery_id is not None
                        else "CLOSE"
                    )
                    new_cache[key] = _CachedNotification(
                        platform=channel.platform,
                        platform_channel_id=channel.platform_channel_id,
                        discord_channel_id=notification.destination_channel_id,
                        streamer_name=channel.channel_name,
                        mention_role=notification.mention_role,
                        last_status=last_status,
                        notification_id=notification.id,
                        v2_channel_id=channel.id,
                    )

                for key, new_entry in new_cache.items():
                    if key in self._cache:
                        old = self._cache[key]
                        new_entry._consecutive_close_count = old._consecutive_close_count
                        new_entry._last_polled_at = old._last_polled_at

                self._cache = new_cache
                self._cache_loaded_at = time.monotonic()
                print(f"[LiveNotification] cache loaded: {len(self._cache)}")
        except Exception as e:
            print(f"[LiveNotification] cache load failed: {e}")
            self._cache_loaded_at = time.monotonic()

    @tasks.loop(seconds=30.0)
    async def check_live_notifications(self):
        print("[LiveNotification] checking live status...")
        try:
            if time.monotonic() - self._cache_loaded_at > _CACHE_TTL:
                await self._load_cache()

            if not self._cache:
                return

            sem = asyncio.Semaphore(5)

            async def bounded(entry: _CachedNotification):
                async with sem:
                    await self.process_notification(entry)

            await asyncio.gather(
                *[bounded(e) for e in self._cache.values()],
                return_exceptions=True,
            )
        except Exception as e:
            print(f"[LiveNotification] loop error: {e}")

    async def process_notification(self, entry: _CachedNotification):
        platform_channel_id = entry.platform_channel_id
        last_status = entry.last_status

        if last_status == "OPEN" and time.monotonic() - entry._last_polled_at < _OPEN_POLL_INTERVAL:
            return

        print(f"[LiveNotification] checking channel: {entry.platform}:{platform_channel_id} (Last: {last_status})")
        entry._last_polled_at = time.monotonic()

        try:
            live_provider = get_live_provider(entry.platform)
            live_status = await live_provider.get_live_status(platform_channel_id)
            if not live_status:
                print(f"[LiveNotification] status lookup failed: {entry.platform}:{platform_channel_id}")
                return

            content = live_status.raw or {}
            current_status = live_status.status

            if current_status not in ("OPEN", "CLOSE"):
                print(f"[LiveNotification] unknown status: {entry.platform}:{platform_channel_id} = {current_status}")
                return

            print(f"[LiveNotification] {entry.platform}:{platform_channel_id} current status: {current_status}")

            if current_status == "OPEN":
                entry._consecutive_close_count = 0
                if last_status == "CLOSE":
                    print(f"[LiveNotification] live started: {entry.platform}:{platform_channel_id}")

                    channel_info = await live_provider.get_channel_info(platform_channel_id) or {}
                    live_data = LiveNotificationData(
                        platform=entry.platform,
                        platform_channel_id=platform_channel_id,
                        streamer_name=entry.streamer_name,
                        live_title=live_status.title or "",
                        category=live_status.category or "",
                        tags=content.get("tags", []),
                        live_url=live_provider.get_live_url(platform_channel_id),
                        thumbnail_url=live_status.thumbnail_url,
                        channel_image_url=channel_info.get("channelImageUrl"),
                        open_date=content.get("openDate"),
                    )

                    if await self._update_status_in_db(entry, "OPEN", content=content):
                        entry.last_status = "OPEN"
                        if not await self.send_live_notification(entry, live_data):
                            await self._mark_delivery_failed(entry, "Discord send failed")
                    else:
                        print(f"[LiveNotification] already delivered or DB update failed: {entry.platform}:{platform_channel_id}")

            elif current_status == "CLOSE" and last_status == "OPEN":
                entry._consecutive_close_count += 1
                if entry._consecutive_close_count >= 2:
                    print(f"[LiveNotification] live closed: {entry.platform}:{platform_channel_id}")
                    if await self._update_status_in_db(entry, "CLOSE"):
                        entry.last_status = "CLOSE"
                        entry._consecutive_close_count = 0
                else:
                    print(f"[LiveNotification] possible close ({entry._consecutive_close_count}/2): {entry.platform}:{platform_channel_id}")
        except Exception as e:
            print(f"[LiveNotification] error {entry.platform}:{platform_channel_id}: {e}")

    async def _update_status_in_db(self, entry: _CachedNotification, status: str, content: dict | None = None) -> bool:
        if not entry.is_v2:
            return False
        return await self._update_v2_status_in_db(entry, status, content)

    async def trigger_live_notification_check(self, platform: str, platform_channel_id: str):
        if time.monotonic() - self._cache_loaded_at > _CACHE_TTL or not self._cache:
            await self._load_cache()

        targets = [
            entry
            for entry in self._cache.values()
            if entry.platform == platform
            and entry.platform_channel_id == platform_channel_id
            and entry.last_status == "CLOSE"
        ]
        if not targets:
            return

        await asyncio.gather(
            *(self.process_notification(entry) for entry in targets),
            return_exceptions=True,
        )

    async def _update_v2_status_in_db(self, entry: _CachedNotification, status: str, content: dict | None = None) -> bool:
        factory = get_session_factory()
        if not factory:
            return False

        try:
            async with factory() as db:
                now = datetime.now(timezone.utc)

                if status == "OPEN":
                    from app.features.chat.service import ChatService

                    await ChatService(db).sync_stream_session(
                        entry.platform_channel_id,
                        entry.platform,
                        live_status_content=content,
                        notify_discord=False,
                    )
                    live_state = await db.get(models.V2ChannelLiveState, entry.v2_channel_id)
                    stream_session_id = live_state.current_stream_session_id if live_state else None

                    if not stream_session_id:
                        latest = (await db.execute(
                            select(models.V2StreamSession)
                            .where(
                                models.V2StreamSession.channel_id == entry.v2_channel_id,
                                models.V2StreamSession.closed_at.is_(None),
                            )
                            .order_by(models.V2StreamSession.opened_at.desc())
                            .limit(1)
                        )).scalar_one_or_none()
                        stream_session_id = latest.id if latest else None

                    if not stream_session_id:
                        return False

                    entry.current_stream_session_id = stream_session_id
                    deliveries_table = models.V2LiveNotificationDelivery.__table__
                    claim_stmt = (
                        pg_insert(deliveries_table)
                        .values(
                            notification_id=entry.notification_id,
                            stream_session_id=stream_session_id,
                            delivered_at=now,
                            delivery_status="success",
                        )
                        .on_conflict_do_nothing(
                            constraint="unique_v2_live_notification_delivery",
                        )
                        .returning(deliveries_table.c.id)
                    )
                    delivery_id = (await db.execute(claim_stmt)).scalar_one_or_none()
                    await db.commit()
                    return delivery_id is not None

                latest = (await db.execute(
                    select(models.V2StreamSession)
                    .where(
                        models.V2StreamSession.channel_id == entry.v2_channel_id,
                        models.V2StreamSession.closed_at.is_(None),
                    )
                    .order_by(models.V2StreamSession.opened_at.desc())
                    .limit(1)
                )).scalar_one_or_none()
                if latest:
                    latest.closed_at = now

                live_state = await db.get(models.V2ChannelLiveState, entry.v2_channel_id)
                if live_state:
                    live_state.status = "CLOSE"
                    live_state.current_stream_session_id = None
                    live_state.last_checked_at = now
                    live_state.raw_status = content

                await db.commit()
                return True
        except Exception as e:
            print(f"[LiveNotification] v2 DB update failed: {e}")
            return False

    async def _mark_delivery_failed(self, entry: _CachedNotification, error_message: str):
        if not entry.is_v2 or not entry.current_stream_session_id:
            return

        factory = get_session_factory()
        if not factory:
            return

        try:
            async with factory() as db:
                delivery = (await db.execute(
                    select(models.V2LiveNotificationDelivery).where(
                        models.V2LiveNotificationDelivery.notification_id == entry.notification_id,
                        models.V2LiveNotificationDelivery.stream_session_id == entry.current_stream_session_id,
                    )
                )).scalar_one_or_none()
                if delivery:
                    delivery.delivery_status = "failed"
                    delivery.error_message = error_message
                    await db.commit()
        except Exception as e:
            print(f"[LiveNotification] delivery failure mark failed: {e}")

    async def send_live_notification(self, entry: _CachedNotification, live_data: LiveNotificationData) -> bool:
        target_channel = self.bot.get_channel(int(entry.discord_channel_id))
        if not target_channel:
            print(f"[LiveNotification] Discord channel not found: {entry.discord_channel_id}")
            return False

        thumbnail_url = live_data.thumbnail_url.replace("{type}", "1080") if live_data.thumbnail_url else None

        embed = discord.Embed(
            title=live_data.live_title,
            description=f"{live_data.streamer_name} 방송 시작!",
            color=0x00D169,
            url=live_data.live_url,
            timestamp=datetime.now(timezone.utc),
        )

        if live_data.category:
            embed.add_field(name="카테고리", value=live_data.category, inline=True)
        if live_data.tags:
            embed.add_field(name="태그", value=" ".join([f"`#{tag}`" for tag in live_data.tags]), inline=False)
        if thumbnail_url:
            embed.set_image(url=thumbnail_url)

        channel_img = live_data.channel_image_url or "https://ssl.pstatic.net/cmstatic/nng/img/img_anonymous_square_gray_opacity2x.png"
        embed.set_thumbnail(url=channel_img)
        embed.set_author(
            name=live_data.streamer_name,
            icon_url=live_data.channel_image_url,
            url=live_data.live_url,
        )
        embed.set_footer(text="방송 알림", icon_url="https://ssl.pstatic.net/static/nng/glive/icon/favicon.png")

        content_msg = (
            f"{entry.mention_role} {live_data.streamer_name} 방송이 시작되었습니다!"
            if entry.mention_role
            else f"{live_data.streamer_name} 방송이 시작되었습니다!"
        )

        try:
            await target_channel.send(content=content_msg, embed=embed)
            print(
                f"[LiveNotification] notification sent: "
                f"{live_data.streamer_name} -> {target_channel.name} ({target_channel.id})"
            )
            return True
        except Exception as e:
            print(f"[LiveNotification] message send failed {live_data.platform_channel_id}: {e}")
            return False

    @check_live_notifications.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()
