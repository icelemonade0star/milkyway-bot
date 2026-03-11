import asyncio
import os
import discord
from discord.ext import tasks, commands
import aiohttp
from sqlalchemy import select
from app.db.database import get_session_factory
from app.db.models import ChzzkNotification as ChzzkNotificationModel
from datetime import datetime, timedelta, timezone

class ChzzkNotification(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.session = None
        self.check_chzzk.start()

    def cog_unload(self):
        self.check_chzzk.cancel()
        if self.session:
            self.bot.loop.create_task(self.session.close())


    async def init_cookies(self):
        print("🍪 [ChzzkNotification] 네이버 쿠키 및 세션을 초기화합니다...")
        try:
            # 기본 접속으로 chzzk 측 쿠키 생성
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                )
            }
            async with self.session.get("https://chzzk.naver.com", headers=headers, timeout=10) as resp:
                resp.raise_for_status() # HTTP 에러 발생 시 예외를 일으킴

            # 네이버 로그인 쿠키 주입
            nid_aut = os.getenv("NID_AUT")
            nid_ses = os.getenv("NID_SES")

            if not nid_aut or not nid_ses:
                print("⚠️ [ChzzkNotification] NID_AUT 또는 NID_SES 환경 변수가 없습니다. 비로그인 상태로 작동합니다.")
                return

            self.session.cookie_jar.update_cookies(
                {"NID_AUT": nid_aut, "NID_SES": nid_ses},
                response_url="https://chzzk.naver.com",
            )
            print("✅ [ChzzkNotification] 네이버 쿠키 주입 완료.")
        except Exception as e:
            print(f"🚨 [ChzzkNotification] 쿠키 초기화 중 심각한 오류 발생: {e}")

    @tasks.loop(minutes=1.0) # 1분에 한 번씩 실행
    async def check_chzzk(self):
        print("👀 [ChzzkNotification] 1분 폴링 루프 도는 중... 확인 중!")
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
        
        url = f"https://api.chzzk.naver.com/service/v1/channels/{chzzk_id}/live-detail"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}

        try:
            async with self.session.get(url, headers=headers, timeout=5) as response:
                # 인증 관련 에러 발생 시 쿠키 갱신 시도
                if response.status in [401, 403]:
                    print(f"[ChzzkNotification] ⚠️ 인증 만료 감지 ({response.status}). 쿠키를 갱신합니다.")
                    await self.init_cookies()
                    # 재시도 (Optional: 재귀 호출 혹은 다음 루프에 맡김. 여기서는 return)
                    return

                if response.status != 200:
                    error_text = await response.text()
                    print(f"[ChzzkNotification] API 에러 {chzzk_id} - 상태코드: {response.status}")
                    print(f"[ChzzkNotification] 에러 상세 내용: {error_text}")
                    return
                
                data = await response.json()
                live_data = data.get("content", {})
                
                # 방송 상태 확인
                if not live_data:
                    current_status = 'CLOSE'
                else:
                    current_status = live_data.get("status")

                print(f"[ChzzkNotification] {chzzk_id} 현재 상태: {current_status}")

                if last_status == 'CLOSE' and current_status == 'OPEN':
                    print(f"[ChzzkNotification] 🟢 방송 시작 감지! {chzzk_id}")
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

    async def send_live_notification(self, setting: ChzzkNotificationModel, live_data: dict):
        # 디스코드 채널 찾기
        target_channel = self.bot.get_channel(int(setting.discord_channel_id))
        if not target_channel:
            print(f"[ChzzkNotification] 디스코드 채널을 찾을 수 없습니다: {setting.discord_channel_id}")
            return

        # 방송 정보 추출
        live_title = live_data.get("liveTitle", "제목 없음")
        category = live_data.get("liveCategoryValue", "카테고리 미지정")
        chzzk_id = setting.chzzk_channel_id
        
        # 채널 정보 추출
        channel_info = live_data.get("channel", {})
        streamer_name = channel_info.get("channelName") or setting.streamer_name or "스트리머"
        channel_image_url = channel_info.get("channelImageUrl")

        # 썸네일 URL 처리 (1080p 해상도로 변경)
        thumbnail_url = live_data.get("liveImageUrl", "").replace("{type}", "1080")

        # 임베드 생성
        embed = discord.Embed(
            title=live_title,
            description=f"{streamer_name} 방송 시작!",
            color=0x00D169, # 치지직 녹색
            url=f"https://chzzk.naver.com/live/{chzzk_id}",
            timestamp=datetime.now()
        )
        
        embed.add_field(name="카테고리", value=category, inline=True)
        if thumbnail_url:
            embed.set_image(url=thumbnail_url)
        if channel_image_url:
            embed.set_thumbnail(url=channel_image_url)
        
        embed.set_author(name=streamer_name, icon_url=channel_image_url, url=f"https://chzzk.naver.com/live/{chzzk_id}")
        embed.set_footer(text="치지직 방송 알림", icon_url="https://ssl.pstatic.net/static/nng/glive/icon/favicon.png")

        mention_role = setting.mention_role
        content = f"{mention_role} {streamer_name} 방송이 시작되었습니다!" if mention_role else f"{streamer_name} 방송이 시작되었습니다!"
        
        try:
            await target_channel.send(content=content, embed=embed)
            print(f"[ChzzkNotification] 알림 전송 성공: {streamer_name} -> {target_channel.name} ({target_channel.id})")
        except Exception as e:
            print(f"[ChzzkNotification] 메시지 전송 실패 {chzzk_id}: {e}")

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
        await self.init_cookies()
