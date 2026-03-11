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
        
        # [Cookie 강제 주입] 헤더에 직접 삽입
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"}

        # 1. 가벼운 Polling API로 상태 먼저 확인
        status_url = f"https://api.chzzk.naver.com/polling/v2/channels/{chzzk_id}/live-status"

        try:
            current_status = None
            async with self.session.get(status_url, headers=headers, timeout=5) as response:
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
                print(f"[ChzzkNotification] 🟢 방송 시작 감지! {chzzk_id} -> 상세 정보 조회")
                
                # 2. 방송이 켜졌을 때만 상세 정보(썸네일 등) API 호출
                detail_url = f"https://api.chzzk.naver.com/service/v1/channels/{chzzk_id}/live-detail"
                
                # [Cookie 주입] 상세 조회 시에만 쿠키 사용
                nid_aut = os.getenv("NID_AUT")
                nid_ses = os.getenv("NID_SES")
                if nid_aut and nid_ses:
                    headers["Cookie"] = f"NID_AUT={nid_aut}; NID_SES={nid_ses}"
                    
                async with self.session.get(detail_url, headers=headers, timeout=5) as detail_res:
                    if detail_res.status == 200:
                        detail_data = await detail_res.json()
                        live_data = detail_data.get("content", {})
                        
                        # 알림 전송 (상세 정보 사용)
                        await self.send_live_notification(notification_setting, live_data)
                        # DB 및 캐시 업데이트
                        await self.update_status(db, notification_setting, 'OPEN', update_time=True)
                    else:
                        print(f"[ChzzkNotification] 상세 정보 조회 실패: {detail_res.status}")
            
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
        live_title = live_data.get("liveTitle")
        category = live_data.get("liveCategoryValue")
        tags = live_data.get("tags")
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
        
        if category:
            embed.add_field(name="카테고리", value=category, inline=True)
        if tags:
            # 태그를 보기 좋게 `#태그` 형식으로 변환
            embed.add_field(name="태그", value=" ".join([f"`#{t}`" for t in tags]), inline=False)
        if thumbnail_url:
            embed.set_image(url=thumbnail_url)
        if channel_image_url:
            embed.set_thumbnail(url=channel_image_url)
        else:
            embed.set_thumbnail(url="https://ssl.pstatic.net/cmstatic/nng/img/img_anonymous_square_gray_opacity2x.png") # 기본 이미지
        
        embed.set_author(name=streamer_name, icon_url=channel_image_url, url=f"https://chzzk.naver.com/{chzzk_id}")
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
