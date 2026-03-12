import asyncio
import json
import os
import discord
from discord.ext import tasks, commands
import aiohttp
from dataclasses import dataclass
from typing import List, Optional
from sqlalchemy import select
from app.db.database import get_session_factory
from app.db.models import ChzzkNotification as ChzzkNotificationModel
from datetime import datetime, timedelta, timezone
from app.api.cookies.chzzk_cookie import ChzzkCookieGetter

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

class ChzzkNotification(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.session = None
        self.cookie_getter = ChzzkCookieGetter()
        self.cookies = {}
        self.check_chzzk.start()

    def cog_unload(self):
        self.check_chzzk.cancel()
        if self.session:
            self.bot.loop.create_task(self.session.close())

    @tasks.loop(seconds=30.0) # 30초에 한 번씩 실행
    async def check_chzzk(self):
        print("👀 [ChzzkNotification] 방송 상태 체크 중... (30s interval)")
        # 쿠키 갱신을 위해 메인 페이지 접속
        try:
            # 1. DB 세션 직접 열기
            factory = get_session_factory()

            if factory is None:
                print("⚠️ DB 세션 팩토리가 없습니다.")
                return

            async with factory() as db:
            
                # 활성화된(is_active=True) 알림 설정만 조회합니다.
                stmt = select(ChzzkNotificationModel).where(ChzzkNotificationModel.is_active == True)
                result = await db.execute(stmt)
                notifications = result.scalars().all()
                
                print(f"✅ [ChzzkNotification] 활성화된 알림 설정 {len(notifications)}개 발견.")

                # 각 알림 설정에 대해 처리
                for notification_setting in notifications:
                    await self.process_notification(db, notification_setting)
                
        except Exception as e:
            print(f"🚨 [ChzzkNotification] 루프 에러 발생: {e}")
    
    async def process_notification(self, db, notification_setting: ChzzkNotificationModel):
        chzzk_id = notification_setting.chzzk_channel_id
        last_status = notification_setting.last_status
        print(f"[ChzzkNotification] 채널 확인 중: {chzzk_id} (Last: {last_status})")

        # 1. 가벼운 Polling API로 상태 먼저 확인
        status_url = f"https://api.chzzk.naver.com/polling/v2/channels/{chzzk_id}/live-status"

        try:
            current_status = None
            async with self.session.get(status_url, timeout=5) as response:
                if response.status != 200:
                    print(f"[ChzzkNotification] Status API 에러 {chzzk_id} - 상태코드: {response.status}")
                    return
                
                data = await response.json()
                content = data.get("content", {})
                
                # 방송 상태 확인
                if not content:
                    current_status = 'CLOSE'
                else:
                    current_status = content.get("status")

            print(f"[ChzzkNotification] {chzzk_id} 현재 상태: {current_status}")

            if last_status == 'CLOSE' and current_status == 'OPEN':
                print(f"[ChzzkNotification] 🟢 방송 시작 감지! {chzzk_id}")

                # 2. 상세 정보(live-detail) 가져오기 (쿠키 사용)
                detail_content = await self.fetch_live_detail(chzzk_id)
                
                # 상세 정보를 못 가져왔으면 Polling 데이터(content)를 사용
                final_content = detail_content if detail_content else content
                
                # 채널 이미지 등 추가 정보 추출
                # live-detail에는 channel 정보가 포함되어 있음
                channel_info = final_content.get("channel", {})
                channel_image = channel_info.get("channelImageUrl")

                # 썸네일은 liveImageUrl 필드 사용
                thumbnail = final_content.get("liveImageUrl")
                
                # LiveNotificationData 객체 생성 및 데이터 세팅
                live_data = LiveNotificationData(
                    channel_id=chzzk_id,
                    streamer_name=notification_setting.streamer_name,
                    live_title=final_content.get("liveTitle", ""),
                    # liveCategoryValue가 우선, 없으면 liveCategory
                    category=final_content.get("liveCategoryValue", "") or final_content.get("liveCategory", ""),
                    tags=final_content.get("tags", []),
                    # 상세 정보가 있으면 썸네일 및 채널 이미지 사용
                    thumbnail_url=thumbnail,
                    channel_image_url=channel_image,
                    open_date=final_content.get("openDate")
                )

                # 알림 전송
                await self.send_live_notification(notification_setting, live_data)
                
                # DB 및 캐시 업데이트
                await self.update_status(db, notification_setting, 'OPEN', update_time=True)
            
            elif last_status == 'OPEN' and current_status == 'CLOSE':
                print(f"[ChzzkNotification] 🔴 방송 종료 감지! {chzzk_id}")
                # DB 및 캐시 업데이트
                await self.update_status(db, notification_setting, 'CLOSE', update_time=False)

        except Exception as e:
            print(f"[ChzzkNotification] 에러 {chzzk_id}: {e}")

    async def fetch_live_detail(self, channel_id: str, retry: bool = True):
        """쿠키가 적용된 세션으로 상세 방송 정보를 가져옵니다."""
        url = f"https://api.chzzk.naver.com/service/v2/channels/{channel_id}/live-detail"
        
        # 쿠키가 없으면 1회 갱신 시도
        if not self.cookies and retry:
            await self.refresh_cookies()

        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("content")
                elif response.status == 500 and retry:
                    print(f"🔄 [ChzzkNotification] 500 에러 감지 ({channel_id}). 쿠키 갱신 후 재시도...")
                    await self.refresh_cookies()
                    return await self.fetch_live_detail(channel_id, retry=False)
                else:
                    print(f"⚠️ [ChzzkNotification] live-detail 조회 실패 ({channel_id}): {response.status}")
                    return None
        except Exception as e:
            print(f"⚠️ [ChzzkNotification] live-detail 요청 중 에러: {e}")
            return None

    async def refresh_cookies(self):
        """ChzzkCookieGetter를 사용하여 쿠키를 갱신하고 메모리에 저장합니다."""
        print("🍪 [ChzzkNotification] 쿠키 갱신 시도 중...")
        naver_id = os.getenv("NAVER_ID")
        naver_pw = os.getenv("NAVER_PW")
        
        if not naver_id or not naver_pw:
            print("⚠️ [ChzzkNotification] 환경변수 NAVER_ID 또는 NAVER_PW가 없습니다.")
            return

        try:
            nid_aut, nid_ses = await self.cookie_getter.login_and_get_cookies(naver_id, naver_pw)
            if nid_aut and nid_ses:
                self.cookies = {"NID_AUT": nid_aut, "NID_SES": nid_ses}
                if self.session:
                    self.session.cookie_jar.update_cookies(self.cookies)
                print(f"✅ [ChzzkNotification] 쿠키 갱신 성공")
            else:
                print(f"❌ [ChzzkNotification] 쿠키 갱신 실패 (로그인 실패)")
        except Exception as e:
            print(f"🚨 [ChzzkNotification] 쿠키 갱신 중 에러 발생: {e}")

    async def send_live_notification(self, setting: ChzzkNotificationModel, live_data: LiveNotificationData):
        # 디스코드 채널 찾기
        target_channel = self.bot.get_channel(int(setting.discord_channel_id))
        if not target_channel:
            print(f"[ChzzkNotification] 디스코드 채널을 찾을 수 없습니다: {setting.discord_channel_id}")
            return

        # 썸네일 URL 처리
        thumbnail_url = live_data.thumbnail_url.replace("{type}", "1080") if live_data.thumbnail_url else None

        # 임베드 생성
        embed = discord.Embed(
            title=live_data.live_title,
            description=f"{live_data.streamer_name} 방송 시작!",
            color=0x00D169, # 치지직 녹색
            url=f"https://chzzk.naver.com/live/{live_data.channel_id}",
            timestamp=datetime.now()
        )
        
        if live_data.category:
            embed.add_field(name="카테고리", value=live_data.category, inline=True)
        if live_data.tags:
            # 태그를 보기 좋게 `#태그` 형식으로 변환
            embed.add_field(name="태그", value=" ".join([f"`#{t}`" for t in live_data.tags]), inline=False)
        if thumbnail_url:
            embed.set_image(url=thumbnail_url)
        else:
            embed.set_image(url="https://ssl.pstatic.net/cmstatic/nng/img/img_anonymous_square_gray_opacity2x.png") # 기본 이미지
        
        # 썸네일 주석처리
        # if live_data.channel_image_url:
        #     embed.set_thumbnail(url=live_data.channel_image_url)
        # else:
        #     embed.set_thumbnail(url="https://ssl.pstatic.net/cmstatic/nng/img/img_anonymous_square_gray_opacity2x.png") # 기본 이미지
        
        embed.set_author(name=live_data.streamer_name, icon_url=live_data.channel_image_url, url=f"https://chzzk.naver.com/{live_data.channel_id}")
        embed.set_footer(text="치지직 방송 알림", icon_url="https://ssl.pstatic.net/static/nng/glive/icon/favicon.png")

        mention_role = setting.mention_role
        content_msg = f"{mention_role} {live_data.streamer_name} 방송이 시작되었습니다!" if mention_role else f"{live_data.streamer_name} 방송이 시작되었습니다!"
        
        try:
            await target_channel.send(content=content_msg, embed=embed)
            print(f"[ChzzkNotification] 알림 전송 성공: {live_data.streamer_name} -> {target_channel.name} ({target_channel.id})")
        except Exception as e:
            print(f"[ChzzkNotification] 메시지 전송 실패 {live_data.channel_id}: {e}")

    async def update_status(self, db, setting: ChzzkNotificationModel, status: str, update_time=False):
        # DB 업데이트
        try:
            setting.last_status = status
            if update_time:
                kst = timezone(timedelta(hours=9))
                setting.last_notified_at = datetime.now(kst)
            await db.commit()
            print(f"[ChzzkNotification] DB 상태 업데이트 완료: {setting.chzzk_channel_id} -> {status}")
        except Exception as e:
            print(f"[ChzzkNotification] DB Update Failed: {e}")
            await db.rollback()
            
    @check_chzzk.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()
        # 루프 시작 전 세션 생성 및 초기 쿠키 세팅 (1회만 실행)
        self.session = aiohttp.ClientSession()
        
        # 시작 시 쿠키 확보 시도
        await self.refresh_cookies()
