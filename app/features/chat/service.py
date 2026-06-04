from fastapi import Depends

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, func
from fastapi import HTTPException
import json

from app.db import models
from app.core.config import MAX_CHAT_RESPONSE_CHARS, MAX_COMMAND_NAME_CHARS, MAX_COMMANDS_PER_CHANNEL, MAX_GREETINGS_PER_CHANNEL
from app.core.database import get_async_db
from app.platforms.registry import get_live_provider
from datetime import datetime, timedelta, timezone

class ChatService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _get_v2_channel(self, platform_channel_id: str, platform: str):
        stmt = select(models.V2Channel).where(
            models.V2Channel.platform == platform,
            models.V2Channel.platform_channel_id == platform_channel_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    def is_response_within_chat_limit(response: str) -> bool:
        parts = [part.strip() for part in response.split('|') if part.strip()]
        targets = parts or [response.strip()]
        return all(len(part) <= MAX_CHAT_RESPONSE_CHARS for part in targets)

    async def update_channel_config(self, channel_id: str, command_prefix: str, language: str, is_active: bool, platform: str):
        try:
            v2_channel = await self._get_v2_channel(channel_id, platform)
            if not v2_channel:
                return None

            config = await self.db.get(models.V2ChannelConfig, v2_channel.id)
            if not config:
                config = models.V2ChannelConfig(channel_id=v2_channel.id)
                self.db.add(config)
            config.command_prefix = command_prefix
            config.language = language
            config.is_active = is_active
            await self.db.commit()
            return config
        except Exception as e:
            await self.db.rollback()
            print(f"[DB Error] {str(e)}")
            raise HTTPException(status_code=500, detail="DB update failed.")


    async def get_channel_config(self, channel_id: str, platform: str):
        try:
            v2_channel = await self._get_v2_channel(channel_id, platform)
            if not v2_channel:
                return None
            return await self.db.get(models.V2ChannelConfig, v2_channel.id)
        except Exception as e:
            await self.db.rollback()
            print(f"[DB Error] {str(e)}")
            raise HTTPException(status_code=500, detail="DB lookup failed.")
        

    async def get_global_commands(self, command: str):
        """
        특정 글로벌 명령어를 DB에서 조회하는 메서드
        """
        try:
            # ORM Select
            # 1. 정확히 일치하는 명령어 조회
            stmt = select(models.V2GlobalChatCommand).where(models.V2GlobalChatCommand.command == command)
            result = await self.db.execute(stmt)
            exact = result.scalar_one_or_none()
            if exact:
                return exact

            # 2. '|' 구분자가 포함된 명령어 조회 (별칭 지원) — LIKE로 DB에서 선필터링
            stmt = select(models.V2GlobalChatCommand).where(
                or_(
                    models.V2GlobalChatCommand.command.like(f'{command}|%'),
                    models.V2GlobalChatCommand.command.like(f'%|{command}'),
                    models.V2GlobalChatCommand.command.like(f'%|{command}|%'),
                )
            )
            result = await self.db.execute(stmt)
            for cmd_obj in result.scalars().all():
                if command in cmd_obj.command.split('|'):
                    return cmd_obj
            
            return None

        except Exception as e:
            await self.db.rollback()
            print(f"[DB Error] {str(e)}")
            raise HTTPException(status_code=500, detail="DB 조회 중 오류가 발생했습니다.")

    async def get_global_command(self, command: str):
        return await self.get_global_commands(command)
        
    async def get_all_global_commands(self):
        """
        활성화된 모든 글로벌 명령어를 조회합니다.
        """
        try:
            # display_order가 0인 명령어는 목록 조회에서 제외
            stmt = select(models.V2GlobalChatCommand).where(
                models.V2GlobalChatCommand.is_active == True,
                models.V2GlobalChatCommand.display_order != 0
            ).order_by(models.V2GlobalChatCommand.display_order.asc())
            result = await self.db.execute(stmt)
            return result.scalars().all()
        except Exception as e:
            await self.db.rollback()
            print(f"[DB Error] {str(e)}")
            return []
            
    async def get_channel_commands(self, channel_id: str, platform: str):
        try:
            v2_channel = await self._get_v2_channel(channel_id, platform)
            if not v2_channel:
                return []

            stmt = select(models.V2ChannelChatCommand).where(
                models.V2ChannelChatCommand.channel_id == v2_channel.id,
                models.V2ChannelChatCommand.is_active == True,
            )
            result = await self.db.execute(stmt)
            return result.scalars().all()
        except Exception as e:
            await self.db.rollback()
            print(f"[DB Error] {str(e)}")
            return []
            

    async def get_chat_command(self, channel_id: str, command: str, platform: str):
        try:
            v2_channel = await self._get_v2_channel(channel_id, platform)
            if not v2_channel:
                return None

            model = models.V2ChannelChatCommand
            channel_key = v2_channel.id

            stmt = select(model).where(
                model.channel_id == channel_key,
                model.command == command,
            )
            result = await self.db.execute(stmt)
            exact = result.scalar_one_or_none()
            if exact:
                return exact

            stmt = select(model).where(
                model.channel_id == channel_key,
                or_(
                    model.command.like(f'{command}|%'),
                    model.command.like(f'%|{command}'),
                    model.command.like(f'%|{command}|%'),
                )
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


    async def add_chat_command(self, channel_id: str, command: str, response: str, platform: str, cooldown_seconds: int | None = None, is_active: bool | None = None):
        try:
            command = command.strip()
            response = response.strip()
            if not command or not response:
                return "empty", None
            if len(command) > MAX_COMMAND_NAME_CHARS:
                return "command_too_long", None
            if not self.is_response_within_chat_limit(response):
                return "response_too_long", None

            existing = await self.get_chat_command(channel_id, command, platform)
            if existing:
                if await self.update_chat_command(channel_id, command, response, platform, cooldown_seconds, is_active):
                    return "updated", existing.command
                return None, None

            global_cmd = await self.get_global_commands(command)
            if global_cmd:
                return "reserved", None

            v2_channel = await self._get_v2_channel(channel_id, platform)
            if not v2_channel:
                return None, None

            model = models.V2ChannelChatCommand
            channel_key = v2_channel.id

            count_stmt = select(func.count()).select_from(model).where(model.channel_id == channel_key)
            count = (await self.db.execute(count_stmt)).scalar()
            if count >= MAX_COMMANDS_PER_CHANNEL:
                return "limit_exceeded", None

            new_cmd = model(
                channel_id=channel_key,
                command=command,
                response=response,
                cooldown_seconds=5 if cooldown_seconds is None else cooldown_seconds,
                is_active=True if is_active is None else is_active,
            )
            self.db.add(new_cmd)
            await self.db.commit()
            return "created", command
        except Exception as e:
            await self.db.rollback()
            print(f"[DB Error] {str(e)}")
            return None, None


    async def update_chat_command(self, channel_id: str, command: str, response: str, platform: str, cooldown_seconds: int | None = None, is_active: bool | None = None):
        try:
            command = command.strip()
            response = response.strip()
            if not command or not response:
                return False

            if not self.is_response_within_chat_limit(response):
                return False

            cmd_obj = await self.get_chat_command(channel_id, command, platform)
            if not cmd_obj:
                return False
            
            cmd_obj.response = response
            if cooldown_seconds is not None:
                cmd_obj.cooldown_seconds = cooldown_seconds
            if is_active is not None:
                cmd_obj.is_active = is_active
            await self.db.commit()
            return True
        except Exception as e:
            await self.db.rollback()
            print(f"[DB Error] {str(e)}")
            return False

    async def delete_chat_command(self, channel_id: str, command: str, platform: str):
        try:
            cmd_obj = await self.get_chat_command(channel_id, command, platform)
            if not cmd_obj:
                return False

            await self.db.delete(cmd_obj)
            await self.db.commit()
            return True
        except Exception as e:
            await self.db.rollback()
            print(f"[DB Error] {str(e)}")
            return False

    # --- 인사말(Greeting) 관련 메서드 ---

    async def get_channel_greetings(self, channel_id: str, platform: str):
        try:
            v2_channel = await self._get_v2_channel(channel_id, platform)
            if not v2_channel:
                return []

            stmt = select(models.V2ChannelGreeting).where(
                models.V2ChannelGreeting.channel_id == v2_channel.id,
                models.V2ChannelGreeting.is_active == True,
            )
            result = await self.db.execute(stmt)
            return result.scalars().all()
        except Exception as e:
            print(f"[DB Error] Greetings fetch failed: {str(e)}")
            return []


    async def get_greeting(self, channel_id: str, keyword: str, platform: str):
        try:
            v2_channel = await self._get_v2_channel(channel_id, platform)
            if not v2_channel:
                return None

            model = models.V2ChannelGreeting
            channel_key = v2_channel.id

            stmt = select(model).where(
                model.channel_id == channel_key,
                model.keyword == keyword,
            )
            result = await self.db.execute(stmt)
            exact = result.scalar_one_or_none()
            if exact:
                return exact

            stmt = select(model).where(
                model.channel_id == channel_key,
                or_(
                    model.keyword.like(f'{keyword}|%'),
                    model.keyword.like(f'%|{keyword}'),
                    model.keyword.like(f'%|{keyword}|%'),
                )
            )
            result = await self.db.execute(stmt)
            for greet_obj in result.scalars().all():
                if keyword in [k.strip() for k in greet_obj.keyword.split('|')]:
                    return greet_obj
            return None
        except Exception as e:
            print(f"[DB Error] Get greeting failed: {str(e)}")
            return None


    async def add_greeting(self, channel_id: str, keyword: str, response: str, platform: str):
        try:
            keyword = keyword.strip()
            response = response.strip()
            if not keyword or not response:
                return "empty", None
            if not self.is_response_within_chat_limit(response):
                return "response_too_long", None

            existing = await self.get_greeting(channel_id, keyword, platform)
            if existing:
                if await self.update_greeting(channel_id, keyword, response, platform):
                    return "updated", existing.keyword
                return None, None

            v2_channel = await self._get_v2_channel(channel_id, platform)
            if not v2_channel:
                return None, None

            model = models.V2ChannelGreeting
            channel_key = v2_channel.id

            count_stmt = select(func.count()).select_from(model).where(model.channel_id == channel_key)
            count = (await self.db.execute(count_stmt)).scalar()
            if count >= MAX_GREETINGS_PER_CHANNEL:
                return "limit_exceeded", None

            new_greeting = model(channel_id=channel_key, keyword=keyword, response=response)
            self.db.add(new_greeting)
            await self.db.commit()
            return "created", keyword
        except Exception as e:
            await self.db.rollback()
            print(f"[DB Error] Add greeting failed: {str(e)}")
            return None, None


    async def update_greeting(self, channel_id: str, keyword: str, response: str, platform: str):
        try:
            keyword = keyword.strip()
            response = response.strip()
            if not keyword or not response:
                return False

            if not self.is_response_within_chat_limit(response):
                return False

            target = await self.get_greeting(channel_id, keyword, platform)
            if not target:
                return False

            target.response = response
            await self.db.commit()
            return True
        except Exception as e:
            await self.db.rollback()
            print(f"[DB Error] Update greeting failed: {str(e)}")
            return False

    async def delete_greeting(self, channel_id: str, keyword: str, platform: str):
        try:
            target = await self.get_greeting(channel_id, keyword, platform)

            if not target:
                return False

            await self.db.delete(target)
            await self.db.commit()
            return True
        except Exception as e:
            await self.db.rollback()
            print(f"[DB Error] Delete greeting failed: {str(e)}")
            return False

    # --- 출석 체크 관련 메서드 ---

    async def process_attendance(self, channel_id: str, user_id: str, user_name: str, platform: str):
        try:
            latest_session = await self.sync_stream_session(channel_id, platform)
            if not latest_session:
                return {"status": "not_streaming"}

            current_opened_at = latest_session.opened_at
            v2_channel = await self._get_v2_channel(channel_id, platform)

            if not v2_channel:
                return None

            previous_session = (await self.db.execute(
                select(models.V2StreamSession).where(
                    models.V2StreamSession.channel_id == v2_channel.id,
                    models.V2StreamSession.opened_at < current_opened_at,
                ).order_by(models.V2StreamSession.opened_at.desc()).limit(1)
            )).scalar_one_or_none()

            attendance = (await self.db.execute(
                select(models.V2ViewerAttendance).where(
                    models.V2ViewerAttendance.channel_id == v2_channel.id,
                    models.V2ViewerAttendance.platform_user_id == user_id,
                )
            )).scalar_one_or_none()

            if not attendance:
                attendance = models.V2ViewerAttendance(
                    channel_id=v2_channel.id,
                    platform_user_id=user_id,
                    user_name=user_name,
                    attendance_count=1,
                    streak_count=1,
                    last_attendance_at=current_opened_at,
                )
                self.db.add(attendance)
                await self.db.commit()
                return {"status": "checked", "streak": 1, "total": 1, "is_new": True}

            if attendance.last_attendance_at == current_opened_at:
                return {
                    "status": "already_checked",
                    "streak": attendance.streak_count,
                    "total": attendance.attendance_count,
                    "is_new": False,
                }

            if previous_session and attendance.last_attendance_at == previous_session.opened_at:
                attendance.streak_count += 1
            else:
                attendance.streak_count = 1

            attendance.attendance_count += 1
            attendance.last_attendance_at = current_opened_at
            attendance.user_name = user_name
            await self.db.commit()
            return {
                "status": "checked",
                "streak": attendance.streak_count,
                "total": attendance.attendance_count,
                "is_new": False,
            }
        except Exception as e:
            await self.db.rollback()
            print(f"[DB Error] Attendance check failed: {str(e)}")
            return None

    async def _mark_stream_closed(self, channel_id: str, platform: str, raw_status: dict | None = None):
        now = datetime.now(timezone.utc)

        v2_channel = await self._get_v2_channel(channel_id, platform)
        if not v2_channel:
            return

        latest_v2 = (await self.db.execute(
            select(models.V2StreamSession)
            .where(
                models.V2StreamSession.channel_id == v2_channel.id,
                models.V2StreamSession.closed_at.is_(None),
            )
            .order_by(models.V2StreamSession.opened_at.desc())
            .limit(1)
        )).scalar_one_or_none()
        if latest_v2:
            latest_v2.closed_at = now

        live_state = await self.db.get(models.V2ChannelLiveState, v2_channel.id)
        if not live_state:
            live_state = models.V2ChannelLiveState(channel_id=v2_channel.id)
            self.db.add(live_state)
        live_state.status = "CLOSE"
        live_state.current_stream_session_id = None
        live_state.last_checked_at = now
        live_state.raw_status = raw_status


    async def sync_stream_session(self, channel_id: str, platform: str):
        """Sync the current live stream session through the platform live provider."""
        from app.redis.redis_service import redis_client

        try:
            cache_key = f"live_status:{channel_id}"
            cached_status = await redis_client.get(cache_key)

            if cached_status:
                if cached_status == "CLOSE":
                    await self._mark_stream_closed(channel_id, platform)
                    await self.db.commit()
                    return None
                content = json.loads(cached_status)
                open_date_str = content.get("openDate")
                if not open_date_str:
                    await self._mark_stream_closed(channel_id, platform, content)
                    await self.db.commit()
                    return None
                kst_tz = timezone(timedelta(hours=9))
                current_opened_at = datetime.strptime(open_date_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=kst_tz)
                stream_title = content.get("liveTitle")
            else:
                provider = get_live_provider(platform)
                live_status = await provider.get_live_status(channel_id)

                if not live_status or live_status.status != "OPEN" or not live_status.opened_at:
                    await redis_client.set(cache_key, "CLOSE", ex=60)
                    await self._mark_stream_closed(channel_id, platform, live_status.raw if live_status else None)
                    await self.db.commit()
                    return None

                content = live_status.raw or {}
                await redis_client.set(cache_key, json.dumps(content), ex=300)
                current_opened_at = live_status.opened_at
                stream_title = live_status.title

            v2_channel = await self._get_v2_channel(channel_id, platform)
            if not v2_channel:
                return None

            v2_session = (await self.db.execute(
                select(models.V2StreamSession).where(
                    models.V2StreamSession.channel_id == v2_channel.id,
                    models.V2StreamSession.opened_at == current_opened_at,
                )
            )).scalar_one_or_none()
            if not v2_session:
                v2_session = models.V2StreamSession(
                    channel_id=v2_channel.id,
                    opened_at=current_opened_at,
                    stream_title=stream_title,
                    category=(content.get("liveCategoryValue") or content.get("liveCategory")) if content else None,
                    thumbnail_url=content.get("liveImageUrl") if content else None,
                    raw_live_response=content,
                )
                self.db.add(v2_session)
                await self.db.flush()

            live_state = await self.db.get(models.V2ChannelLiveState, v2_channel.id)
            if not live_state:
                live_state = models.V2ChannelLiveState(channel_id=v2_channel.id)
                self.db.add(live_state)
            live_state.status = "OPEN"
            live_state.current_stream_session_id = v2_session.id
            live_state.last_checked_at = datetime.now(timezone.utc)
            live_state.raw_status = content

            await self.db.commit()
            return v2_session
        except Exception as e:
            await self.db.rollback()
            print(f"[DB Error] Sync stream session failed: {str(e)}")
            return None

async def get_chat_service(db: AsyncSession = Depends(get_async_db)):
    return ChatService(db)

   
