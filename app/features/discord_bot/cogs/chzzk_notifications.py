import time
import asyncio
import discord
from discord.ext import tasks, commands
import aiohttp
from dataclasses import dataclass, field
from typing import List, Optional
from sqlalchemy import select
from app.core.database import get_session_factory
from app.db.models import ChzzkNotification as ChzzkNotificationModel
from datetime import datetime, timedelta, timezone
from app.core.chzzk_api import ChzzkAPIClient

_CACHE_TTL = 300.0          # 5분마다 DB 재조회
_OPEN_POLL_INTERVAL = 300.0  # OPEN 채널은 5분마다만 확인

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
    # API가 순간적으로 CLOSE를 잘못 반환하는 경우를 걸러내기 위한 연속 카운터.
    # 캐시 갱신 시에도 보존된다 (_load_cache 참고).
    _consecutive_close_count: int = field(default=0, repr=False)
    # 마지막으로 실제 API를 호출한 시각 (monotonic). OPEN 채널 폴링 간격 제어에 사용.
    _last_polled_at: float = field(default=0.0, repr=False)


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
            asyncio.create_task(self.session.close())
        if self.chzzk_client:
            asyncio.create_task(self.chzzk_client.close())
        _active_cog = None

    async def _load_cache(self):
        factory = get_session_factory()
        if not factory:
            return

        try:
            async with factory() as db:
                stmt = select(ChzzkNotificationModel).where(ChzzkNotificationModel.is_active == True)
                result = await db.execute(stmt)
                notifications = result.scalars().all()

                new_cache = {
                    n.chzzk_channel_id: _CachedNotification(
                        chzzk_channel_id=n.chzzk_channel_id,
                        discord_channel_id=n.discord_channel_id,
                        streamer_name=n.streamer_name,
                        mention_role=getattr(n, "mention_role", None),
                        last_status=n.last_status,
                    )
                    for n in notifications
                }

                # 캐시 갱신 시 인메모리 상태 유지 (갱신으로 카운터/타이머가 리셋되지 않도록)
                for chzzk_id, new_entry in new_cache.items():
                    if chzzk_id in self._cache:
                        old = self._cache[chzzk_id]
                        new_entry._consecutive_close_count = old._consecutive_close_count
                        new_entry._last_polled_at = old._last_polled_at

                self._cache = new_cache
                self._cache_loaded_at = time.monotonic()
                print(f"✅ [ChzzkNotification] 캐시 로드 완료: {len(self._cache)}개")
        except Exception as e:
            print(f"🚨 [ChzzkNotification] 캐시 로드 실패: {e}")
            # 실패해도 TTL 적용 — DB를 매 틱마다 재시도하지 않도록
            self._cache_loaded_at = time.monotonic()

    @tasks.loop(seconds=30.0)
    async def check_chzzk(self):
        print("👀 [ChzzkNotification] 방송 상태 체크 중... (30s interval)")
        try:
            if time.monotonic() - self._cache_loaded_at > _CACHE_TTL:
                await self._load_cache()

            if not self._cache:
                return

            # 채널 수가 늘어도 30초 주기를 지킬 수 있도록 병렬 처리 (최대 5개 동시 요청)
            sem = asyncio.Semaphore(5)

            async def bounded(entry: _CachedNotification):
                async with sem:
                    await self.process_notification(entry)

            await asyncio.gather(
                *[bounded(e) for e in self._cache.values()],
                return_exceptions=True,
            )

        except Exception as e:
            print(f"🚨 [ChzzkNotification] 루프 에러 발생: {e}")

    async def process_notification(self, entry: _CachedNotification):
        chzzk_id = entry.chzzk_channel_id
        last_status = entry.last_status

        # OPEN 채널은 5분마다만 확인 — 이미 방송 중인 채널에 불필요한 API 요청 방지
        if last_status == "OPEN" and time.monotonic() - entry._last_polled_at < _OPEN_POLL_INTERVAL:
            return

        print(f"[ChzzkNotification] 채널 확인 중: {chzzk_id} (Last: {last_status})")
        entry._last_polled_at = time.monotonic()

        status_url = f"https://api.chzzk.naver.com/polling/v2/channels/{chzzk_id}/live-status"

        try:
            content = {}
            current_status = None
            async with self.session.get(status_url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                if response.status != 200:
                    print(f"[ChzzkNotification] Status API 에러 {chzzk_id} - 상태코드: {response.status}")
                    return

                data = await response.json()
                content = data.get("content") or {}
                current_status = content.get("status")

            if current_status not in ("OPEN", "CLOSE"):
                print(f"[ChzzkNotification] ⚠️ 알 수 없는 상태값: {chzzk_id} = {current_status}")
                return

            print(f"[ChzzkNotification] {chzzk_id} 현재 상태: {current_status}")

            if current_status == "OPEN":
                entry._consecutive_close_count = 0
                if last_status == "CLOSE":
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

            elif current_status == "CLOSE" and last_status == "OPEN":
                # API가 일시적으로 CLOSE를 반환하는 경우를 걸러낸다.
                # 2회 연속 CLOSE일 때만 실제 종료로 처리한다 (약 30~60초 딜레이).
                entry._consecutive_close_count += 1
                if entry._consecutive_close_count >= 2:
                    print(f"[ChzzkNotification] 🔴 방송 종료 확정! {chzzk_id}")
                    if await self._update_status_in_db(chzzk_id, "CLOSE", update_time=False):
                        entry.last_status = "CLOSE"
                        entry._consecutive_close_count = 0
                else:
                    print(f"[ChzzkNotification] 🟡 방송 종료 의심 ({entry._consecutive_close_count}/2): {chzzk_id}")

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

                # 방송 시작 시 스트림 세션 동기화
                if status == "OPEN" and content:
                    from app.features.chat.service import ChatService
                    await ChatService(db).sync_stream_session(chzzk_id)

                # 방송 종료 시 세션 종료 시각 기록
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
            timestamp=datetime.now(timezone.utc),
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
