import time
import asyncio
import discord
from discord.ext import tasks, commands
import aiohttp
from dataclasses import dataclass
from typing import List, Optional
from sqlalchemy import select
from app.core.database import get_session_factory
from app.db.models import ChzzkNotification as ChzzkNotificationModel
from datetime import datetime, timedelta, timezone
from app.core.chzzk_api import ChzzkAPIClient

_CACHE_TTL = 300.0  # 5분마다 DB 재조회

# 활성 Cog 인스턴스 — 외부에서 캐시 무효화 시 사용
_active_cog: Optional["ChzzkNotification"] = None


def invalidate_notification_cache():
    """알림 설정이 변경됐을 때 외부(handler.py 등)에서 호출해 캐시를 즉시 만료."""
    if _active_cog is not None:
        _active_cog._cache_loaded_at = 0.0


@dataclass
class LiveNotificationData:
    channel_id: str
    streamer_name: str
    live_title: str
    category: str
    tags: List[str]
    thumbnail_url: Optional[str] = None
    channel_image_url: Optional[str] = None
    open_date: Optional[str] = None


@dataclass
class _CachedNotification:
    """DB 모델과 분리된 경량 캐시 엔트리."""
    chzzk_channel_id: str
    discord_channel_id: str
    streamer_name: str
    mention_role: Optional[str]
    last_status: str


class ChzzkNotification(commands.Cog):
    def __init__(self, bot):
        global _active_cog
        self.bot = bot
        self.session = None
        self.chzzk_client = ChzzkAPIClient()
        self._cache: dict[str, _CachedNotification] = {}
        self._cache_loaded_at: float = 0.0
        _active_cog = self
        self.check_chzzk.start()

    def cog_unload(self):
        global _active_cog
        self.check_chzzk.cancel()
        if self.session:
            self.bot.loop.create_task(self.session.close())
        if self.chzzk_client:
            self.bot.loop.create_task(self.chzzk_client.close())
        _active_cog = None

    async def _load_cache(self):
        factory = get_session_factory()
        if not factory:
            return

        async with factory() as db:
            stmt = select(ChzzkNotificationModel).where(ChzzkNotificationModel.is_active == True)
            result = await db.execute(stmt)
            notifications = result.scalars().all()

            self._cache = {
                n.chzzk_channel_id: _CachedNotification(
                    chzzk_channel_id=n.chzzk_channel_id,
                    discord_channel_id=n.discord_channel_id,
                    streamer_name=n.streamer_name,
                    mention_role=getattr(n, "mention_role", None),
                    last_status=n.last_status,
                )
                for n in notifications
            }
            self._cache_loaded_at = time.monotonic()
            print(f"✅ [ChzzkNotification] 캐시 로드 완료: {len(self._cache)}개")

    @tasks.loop(seconds=30.0)
    async def check_chzzk(self):
        print("👀 [ChzzkNotification] 방송 상태 체크 중... (30s interval)")
        try:
            # 5분 경과 또는 캐시 미로드 시에만 DB 재조회
            if time.monotonic() - self._cache_loaded_at > _CACHE_TTL:
                await self._load_cache()

            if not self._cache:
                return

            for entry in list(self._cache.values()):
                await self.process_notification(entry)

        except Exception as e:
            print(f"🚨 [ChzzkNotification] 루프 에러 발생: {e}")

    async def process_notification(self, entry: _CachedNotification):
        chzzk_id = entry.chzzk_channel_id
        last_status = entry.last_status
        print(f"[ChzzkNotification] 채널 확인 중: {chzzk_id} (Last: {last_status})")

        status_url = f"https://api.chzzk.naver.com/polling/v2/channels/{chzzk_id}/live-status"

        try:
            current_status = None
            async with self.session.get(status_url, timeout=5) as response:
                if response.status != 200:
                    print(f"[ChzzkNotification] Status API 에러 {chzzk_id} - 상태코드: {response.status}")
                    return

                data = await response.json()
                content = data.get("content", {})
                current_status = content.get("status") if content else "CLOSE"

            print(f"[ChzzkNotification] {chzzk_id} 현재 상태: {current_status}")

            if last_status == "CLOSE" and current_status == "OPEN":
                print(f"[ChzzkNotification] 🟢 방송 시작 감지! {chzzk_id}")

                channel_info = await self.chzzk_client.get_channel_info(chzzk_id) or {}
                live_data = LiveNotificationData(
                    channel_id=chzzk_id,
                    streamer_name=entry.streamer_name,
                    live_title=content.get("liveTitle", ""),
                    category=content.get("liveCategoryValue", "") or content.get("liveCategory", ""),
                    tags=content.get("tags", []),
                    thumbnail_url=content.get("liveImageUrl"),
                    channel_image_url=channel_info.get("channelImageUrl"),
                    open_date=content.get("openDate"),
                )

                # DB를 먼저 갱신 — 실패 시 알림 발송 스킵해 재시작 후 중복 알림 방지
                if await self._update_status_in_db(chzzk_id, "OPEN", update_time=True, content=content):
                    entry.last_status = "OPEN"
                    await self.send_live_notification(entry, live_data)
                else:
                    print(f"[ChzzkNotification] ⚠️ DB 업데이트 실패, 알림 발송 스킵: {chzzk_id}")

            elif last_status == "OPEN" and current_status == "CLOSE":
                print(f"[ChzzkNotification] 🔴 방송 종료 감지! {chzzk_id}")
                if await self._update_status_in_db(chzzk_id, "CLOSE", update_time=False):
                    entry.last_status = "CLOSE"

        except Exception as e:
            print(f"[ChzzkNotification] 에러 {chzzk_id}: {e}")

    async def _update_status_in_db(self, chzzk_id: str, status: str, update_time: bool, content: dict = None) -> bool:
        """상태가 실제로 바뀔 때만 호출 — DB 세션을 자체적으로 관리. 성공 여부 반환."""
        factory = get_session_factory()
        if not factory:
            return False

        try:
            async with factory() as db:
                stmt = select(ChzzkNotificationModel).where(ChzzkNotificationModel.chzzk_channel_id == chzzk_id)
                setting = (await db.execute(stmt)).scalar_one_or_none()
                if not setting:
                    return False

                setting.last_status = status
                if update_time:
                    kst = timezone(timedelta(hours=9))
                    setting.last_notified_at = datetime.now(kst)

                if status == "OPEN" and content:
                    from app.features.chat.service import ChatService
                    await ChatService(db).sync_stream_session(chzzk_id)

                if status == "CLOSE":
                    from app.db.models import StreamSession
                    stmt2 = (
                        select(StreamSession)
                        .where(
                            StreamSession.chzzk_channel_id == chzzk_id,
                            StreamSession.closed_at.is_(None),
                        )
                        .order_by(StreamSession.opened_at.desc())
                        .limit(1)
                    )
                    latest = (await db.execute(stmt2)).scalar_one_or_none()
                    if latest:
                        latest.closed_at = datetime.now(timezone(timedelta(hours=9)))

                await db.commit()
                print(f"[ChzzkNotification] DB 상태 업데이트 완료: {chzzk_id} -> {status}")
                return True
        except Exception as e:
            print(f"[ChzzkNotification] DB Update Failed: {e}")
            return False

    async def send_live_notification(self, entry: _CachedNotification, live_data: LiveNotificationData):
        target_channel = self.bot.get_channel(int(entry.discord_channel_id))
        if not target_channel:
            print(f"[ChzzkNotification] 디스코드 채널을 찾을 수 없습니다: {entry.discord_channel_id}")
            return

        thumbnail_url = live_data.thumbnail_url.replace("{type}", "1080") if live_data.thumbnail_url else None

        embed = discord.Embed(
            title=live_data.live_title,
            description=f"{live_data.streamer_name} 방송 시작!",
            color=0x00D169,
            url=f"https://chzzk.naver.com/live/{live_data.channel_id}",
            timestamp=datetime.now(),
        )

        if live_data.category:
            embed.add_field(name="카테고리", value=live_data.category, inline=True)
        if live_data.tags:
            embed.add_field(name="태그", value=" ".join([f"`#{t}`" for t in live_data.tags]), inline=False)

        channel_img = live_data.channel_image_url or "https://ssl.pstatic.net/cmstatic/nng/img/img_anonymous_square_gray_opacity2x.png"
        embed.set_thumbnail(url=channel_img)
        embed.set_author(name=live_data.streamer_name, icon_url=live_data.channel_image_url, url=f"https://chzzk.naver.com/{live_data.channel_id}")
        embed.set_footer(text="치지직 방송 알림", icon_url="https://ssl.pstatic.net/static/nng/glive/icon/favicon.png")

        mention_role = entry.mention_role
        content_msg = (
            f"{mention_role} {live_data.streamer_name} 방송이 시작되었습니다!"
            if mention_role
            else f"{live_data.streamer_name} 방송이 시작되었습니다!"
        )

        try:
            await target_channel.send(content=content_msg, embed=embed)
            print(f"[ChzzkNotification] 알림 전송 성공: {live_data.streamer_name} -> {target_channel.name} ({target_channel.id})")
        except Exception as e:
            print(f"[ChzzkNotification] 메시지 전송 실패 {live_data.channel_id}: {e}")

    @check_chzzk.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()
        self.session = aiohttp.ClientSession()
