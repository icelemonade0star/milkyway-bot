from fastapi import Depends

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from fastapi import HTTPException
from app.db.models import ChannelConfig, GlobalCommand, ChatCommand, ChatGreeting, Attendance, StreamSession
from app.core.database import get_async_db
from datetime import datetime, timedelta, timezone

class ChatService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def set_channel_config(self, channel_id: str):
        """
        채널 설정 정보를 DB에 저장하는 메서드
        """
        try:
            # ORM: 없으면 생성, 있으면 무시 (get_or_create 패턴)
            config = await self.db.get(ChannelConfig, channel_id)
            if not config:
                config = ChannelConfig(channel_id=channel_id)
                self.db.add(config)
                await self.db.commit()
            
            return config

        except Exception as e:
            # 에러 발생 시 롤백
            await self.db.rollback()
            print(f"[DB Error] {str(e)}")
            raise HTTPException(status_code=500, detail="DB 저장 중 오류가 발생했습니다.")
        
    async def update_channel_config(self, channel_id: str, command_prefix: str, language: str, is_active: bool):
        """
        채널 설정 정보를 DB에 업데이트하는 메서드
        """
        try:
            # ORM Update
            stmt = (
                update(ChannelConfig)
                .where(ChannelConfig.channel_id == channel_id)
                .values(command_prefix=command_prefix, language=language, is_active=is_active)
                .execution_options(synchronize_session="fetch") # 현재 세션의 객체도 업데이트
            )
            await self.db.execute(stmt)
            await self.db.commit()
            
            return await self.get_channel_config(channel_id)

        except Exception as e:
            # 에러 발생 시 롤백
            await self.db.rollback()
            print(f"[DB Error] {str(e)}")
            raise HTTPException(status_code=500, detail="DB 업데이트 중 오류가 발생했습니다.")

    async def get_channel_config(self, channel_id: str):
        """
        채널 설정 정보를 DB에서 조회하는 메서드
        """
        try:
            # ORM Get
            config = await self.db.get(ChannelConfig, channel_id)
            return config

        except Exception as e:
            await self.db.rollback()
            print(f"[DB Error] {str(e)}")
            raise HTTPException(status_code=500, detail="DB 조회 중 오류가 발생했습니다.")
        
    async def get_global_commands(self, command: str):
        """
        특정 글로벌 명령어를 DB에서 조회하는 메서드
        """
        try:
            # ORM Select
            # 1. 정확히 일치하는 명령어 조회
            stmt = select(GlobalCommand).where(GlobalCommand.command == command)
            result = await self.db.execute(stmt)
            exact = result.scalar_one_or_none()
            if exact:
                return exact

            # 2. '|' 구분자가 포함된 명령어 조회 (별칭 지원)
            stmt = select(GlobalCommand).where(GlobalCommand.command.contains('|'))
            result = await self.db.execute(stmt)
            for cmd_obj in result.scalars().all():
                if command in cmd_obj.command.split('|'):
                    return cmd_obj
            
            return None

        except Exception as e:
            await self.db.rollback()
            print(f"[DB Error] {str(e)}")
            raise HTTPException(status_code=500, detail="DB 조회 중 오류가 발생했습니다.")
        
    async def get_all_global_commands(self):
        """
        활성화된 모든 글로벌 명령어를 조회합니다.
        """
        try:
            # display_order가 0인 명령어는 목록 조회에서 제외
            stmt = select(GlobalCommand).where(
                GlobalCommand.is_active == True,
                GlobalCommand.display_order != 0
            ).order_by(GlobalCommand.display_order.asc())
            result = await self.db.execute(stmt)
            return result.scalars().all()
        except Exception as e:
            await self.db.rollback()
            print(f"[DB Error] {str(e)}")
            return []
            
    async def get_channel_commands(self, channel_id: str):
        """
        특정 채널의 활성화된 커스텀 명령어 목록을 조회합니다.
        """
        try:
            stmt = select(ChatCommand).where(
                ChatCommand.channel_id == channel_id, 
                ChatCommand.is_active == True
            )
            result = await self.db.execute(stmt)
            return result.scalars().all()
        except Exception as e:
            await self.db.rollback()
            print(f"[DB Error] {str(e)}")
            return []
            
    async def get_chat_command(self, channel_id: str, command: str):
        """
        특정 채널의 특정 커스텀 명령어를 조회합니다.
        """
        try:
            # 1. 정확히 일치하는 명령어 조회
            stmt = select(ChatCommand).where(
                ChatCommand.channel_id == channel_id, 
                ChatCommand.command == command
            )
            result = await self.db.execute(stmt)
            exact = result.scalar_one_or_none()
            if exact:
                return exact

            # 2. '|' 구분자가 포함된 명령어 조회 (별칭 지원)
            stmt = select(ChatCommand).where(
                ChatCommand.channel_id == channel_id,
                ChatCommand.command.contains('|')
            )
            result = await self.db.execute(stmt)
            for cmd_obj in result.scalars().all():
                if command in cmd_obj.command.split('|'):
                    return cmd_obj
            
            return None
        except Exception as e:
            await self.db.rollback()
            print(f"[DB Error] {str(e)}")
            return None

    async def add_chat_command(self, channel_id: str, command: str, response: str):
        try:
            # 중복 체크
            existing = await self.get_chat_command(channel_id, command)
            if existing:
                return await self.update_chat_command(channel_id, command, response)
            
            # 글로벌 명령어 중복 확인
            global_cmd = await self.get_global_commands(command)
            if global_cmd:
                return False

            new_cmd = ChatCommand(channel_id=channel_id, command=command, response=response)
            self.db.add(new_cmd)
            await self.db.commit()
            return True
        except Exception as e:
            await self.db.rollback()
            print(f"[DB Error] {str(e)}")
            return False

    async def update_chat_command(self, channel_id: str, command: str, response: str):
        try:
            cmd_obj = await self.get_chat_command(channel_id, command)
            if not cmd_obj:
                return False
            
            cmd_obj.response = response
            await self.db.commit()
            return True
        except Exception as e:
            await self.db.rollback()
            print(f"[DB Error] {str(e)}")
            return False

    async def delete_chat_command(self, channel_id: str, command: str):
        try:
            cmd_obj = await self.get_chat_command(channel_id, command)
            if not cmd_obj:
                return False
            
            await self.db.delete(cmd_obj)
            await self.db.commit()
            return True
        except Exception as e:
            await self.db.rollback()
            print(f"[DB Error] {str(e)}")
            return False

    # --- 인삿말(Greeting) 관련 메서드 ---

    async def get_channel_greetings(self, channel_id: str):
        """특정 채널의 모든 인삿말 조회"""
        try:
            stmt = select(ChatGreeting).where(ChatGreeting.channel_id == channel_id)
            result = await self.db.execute(stmt)
            return result.scalars().all()
        except Exception as e:
            print(f"[DB Error] Greetings fetch failed: {str(e)}")
            return []

    async def get_greeting(self, channel_id: str, keyword: str):
        """특정 인삿말 조회"""
        try:
            stmt = select(ChatGreeting).where(
                ChatGreeting.channel_id == channel_id,
                ChatGreeting.keyword == keyword
            )
            result = await self.db.execute(stmt)
            return result.scalar_one_or_none()
        except Exception as e:
            print(f"[DB Error] Get greeting failed: {str(e)}")
            return None

    async def create_greeting(self, channel_id: str, keyword: str, response: str):
        """인삿말 등록 (중복 시 실패)"""
        try:
            existing = await self.get_greeting(channel_id, keyword)
            if existing:
                return False
            
            new_greeting = ChatGreeting(channel_id=channel_id, keyword=keyword, response=response)
            self.db.add(new_greeting)
            await self.db.commit()
            return True
        except Exception as e:
            await self.db.rollback()
            print(f"[DB Error] Create greeting failed: {str(e)}")
            return False

    async def update_greeting(self, channel_id: str, keyword: str, response: str):
        """인삿말 수정 (없으면 실패)"""
        try:
            existing = await self.get_greeting(channel_id, keyword)
            if not existing:
                return False
            
            existing.response = response
            await self.db.commit()
            return True
        except Exception as e:
            await self.db.rollback()
            print(f"[DB Error] Update greeting failed: {str(e)}")
            return False

    async def delete_greeting(self, channel_id: str, keyword: str):
        try:
            stmt = select(ChatGreeting).where(
                ChatGreeting.channel_id == channel_id,
                ChatGreeting.keyword == keyword
            )
            result = await self.db.execute(stmt)
            target = result.scalar_one_or_none()
            
            if not target:
                return False
                
            await self.db.delete(target)
            await self.db.commit()
            return True
        except Exception as e:
            await self.db.rollback()
            print(f"[DB Error] Delete greeting failed: {str(e)}")
            return False

    # --- 출석 체크 (Attendance) 관련 메서드 ---

    async def process_attendance(self, channel_id: str, user_id: str, user_name: str):
        """
        출석 체크를 수행하고 결과를 반환합니다 (방송 세션 단위 기준).
        """
        try:
            # 1. 방송 세션 확인 및 동기화 (방송 중이 아니거나, 데이터가 없으면 None 반환)
            latest_session = await self.sync_stream_session(channel_id)

            if not latest_session:
                # sync_stream_session에서 실패하면 방송 중이 아니거나, API 오류, openDate 없음 등의 이유.
                # 사용자에게는 방송 중이 아니라는 메시지로 통일하여 안내.
                return {"status": "not_streaming"}

            current_opened_at = latest_session.opened_at

            # 2. 이전 방송 세션 조회 (연속 출석 체크용)
            previous_session = (await self.db.execute(
                select(StreamSession).where(
                    StreamSession.chzzk_channel_id == channel_id,
                    StreamSession.opened_at < current_opened_at
                ).order_by(StreamSession.opened_at.desc()).limit(1)
            )).scalar_one_or_none()

            # 3. 기존 출석 기록 확인
            stmt_att = select(Attendance).where(
                Attendance.channel_id == channel_id,
                Attendance.user_id == user_id
            )
            attendance = (await self.db.execute(stmt_att)).scalar_one_or_none()

            if not attendance:
                # 첫 출석
                new_attendance = Attendance(
                    channel_id=channel_id,
                    user_id=user_id,
                    user_name=user_name,
                    attendance_count=1,
                    streak_count=1,
                    last_attendance_at=current_opened_at
                )
                self.db.add(new_attendance)
                await self.db.commit()
                return {"status": "checked", "streak": 1, "total": 1, "is_new": True}

            # 중복 출석 확인 (단계 3)
            if attendance.last_attendance_at == current_opened_at:
                return {
                    "status": "already_checked", 
                    "streak": attendance.streak_count, 
                    "total": attendance.attendance_count, 
                    "is_new": False
                }

            # 4. 연속 출석 검사 (단계 4)
            if previous_session and attendance.last_attendance_at == previous_session.opened_at:
                attendance.streak_count += 1
            else:
                attendance.streak_count = 1

            # 5. 출석 업데이트 (단계 5)
            attendance.attendance_count += 1
            attendance.last_attendance_at = current_opened_at
            attendance.user_name = user_name
            
            await self.db.commit()
            return {"status": "checked", "streak": attendance.streak_count, "total": attendance.attendance_count, "is_new": False}

        except Exception as e:
            await self.db.rollback()
            print(f"[DB Error] Attendance check failed: {str(e)}")
            return None

    async def sync_stream_session(self, channel_id: str):
        """
        현재 방송 상태를 확인하고, 방송 중이면 StreamSession을 기록합니다.
        """
        import httpx
        try:
            status_url = f"https://api.chzzk.naver.com/polling/v2/channels/{channel_id}/live-status"
            content = {}
            async with httpx.AsyncClient() as client:
                res = await client.get(status_url, timeout=5)
                if res.status_code != 200:
                    return None # API 실패
                content = res.json().get("content", {})
                if not content or content.get("status") != "OPEN":
                    return None # 방송 중 아님

            open_date_str = content.get("openDate")
            if not open_date_str:
                return None # 방송 시작 정보 없음

            kst_tz = timezone(timedelta(hours=9))
            current_opened_at = datetime.strptime(open_date_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=kst_tz)

            stmt_find_session = select(StreamSession).where(
                StreamSession.chzzk_channel_id == channel_id,
                StreamSession.opened_at == current_opened_at
            )
            existing_session = (await self.db.execute(stmt_find_session)).scalar_one_or_none()

            if not existing_session:
                new_session = StreamSession(chzzk_channel_id=channel_id, opened_at=current_opened_at, stream_title=content.get("liveTitle"))
                self.db.add(new_session)
                await self.db.commit()
                return new_session
            
            return existing_session
        except Exception as e:
            await self.db.rollback()
            print(f"[DB Error] Sync stream session failed: {str(e)}")
            return None

async def get_chat_service(db: AsyncSession = Depends(get_async_db)):
    return ChatService(db)

   