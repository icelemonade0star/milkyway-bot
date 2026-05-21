import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models
from app.features.auth.service import AuthService
from app.features.chat.service import ChatService
from app.redis.redis_service import RedisConfigService

logger = logging.getLogger("DashboardService")


class DashboardService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.chat_service = ChatService(db)
        self.redis_service = RedisConfigService()

    async def get_dashboard_data(self, channel_id: str):
        auth_service = AuthService(self.db)
        auth_token = await auth_service.get_auth_token_by_id(channel_id)
        if not auth_token:
            return None

        config = await self.db.get(models.ChannelConfig, channel_id)

        attendance_stats = (await self.db.execute(
            select(
                func.count(models.Attendance.id),
                func.coalesce(func.sum(models.Attendance.attendance_count), 0),
            )
            .where(models.Attendance.channel_id == channel_id)
        )).one()
        attendance_users, attendance_total = attendance_stats

        notification = (await self.db.execute(
            select(models.ChzzkNotification).where(models.ChzzkNotification.chzzk_channel_id == channel_id)
        )).scalar_one_or_none()

        commands = (await self.db.execute(
            select(models.ChatCommand)
            .where(models.ChatCommand.channel_id == channel_id)
            .order_by(models.ChatCommand.command.asc())
        )).scalars().all()

        greetings = (await self.db.execute(
            select(models.ChatGreeting)
            .where(models.ChatGreeting.channel_id == channel_id)
            .order_by(models.ChatGreeting.keyword.asc())
        )).scalars().all()

        attendance_rank = (await self.db.execute(
            select(models.Attendance)
            .where(models.Attendance.channel_id == channel_id)
            .order_by(models.Attendance.attendance_count.desc(), models.Attendance.streak_count.desc())
            .limit(10)
        )).scalars().all()

        return {
            "auth": auth_token,
            "config": config,
            "notification": notification,
            "commands": commands,
            "greetings": greetings,
            "attendance_rank": attendance_rank,
            "stats": {
                "attendance_users": attendance_users,
                "attendance_total": attendance_total,
            },
        }

    async def save_command(self, channel_id: str, command: str, response: str, cooldown_seconds: int) -> bool:
        command = command.strip()
        response = response.strip()
        try:
            command_obj = await self.chat_service.get_chat_command(channel_id, command)
            if command_obj:
                command_obj.response = response
                command_obj.cooldown_seconds = cooldown_seconds
                await self.db.commit()
                return True

            global_cmd = await self.chat_service.get_global_command(command)
            if global_cmd:
                return False

            self.db.add(models.ChatCommand(
                channel_id=channel_id,
                command=command,
                response=response,
                cooldown_seconds=cooldown_seconds,
            ))
            await self.db.commit()
            return True
        except Exception as e:
            await self.db.rollback()
            logger.warning("Dashboard command save failed: %s", e)
            return False

    async def delete_command(self, channel_id: str, command: str) -> bool:
        return await self.chat_service.delete_chat_command(channel_id, command.strip())

    async def save_greeting(self, channel_id: str, keyword: str, response: str) -> bool:
        status, actual_keyword = await self.chat_service.add_greeting(
            channel_id,
            keyword.strip(),
            response.strip(),
        )
        if status in ("created", "updated") and actual_keyword:
            if not await self.redis_service.add_greeting_cache(channel_id, actual_keyword, response.strip()):
                logger.warning("Greeting cache update failed: channel_id=%s keyword=%s", channel_id, actual_keyword)
            return True
        return False

    async def delete_greeting(self, channel_id: str, keyword: str) -> bool:
        target = await self.chat_service.get_greeting(channel_id, keyword.strip())
        if not target:
            return False

        actual_keyword = target.keyword
        try:
            await self.db.delete(target)
            await self.db.commit()
        except Exception as e:
            await self.db.rollback()
            logger.warning("Dashboard greeting delete failed: %s", e)
            return False

        if not await self.redis_service.delete_greeting_cache(channel_id, actual_keyword):
            logger.warning("Greeting cache delete failed: channel_id=%s keyword=%s", channel_id, actual_keyword)
        return True
