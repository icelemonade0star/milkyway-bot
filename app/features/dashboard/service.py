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
        v2_channel = await auth_service.get_v2_channel_by_platform_id("chzzk", channel_id)

        config = await self.chat_service.get_channel_config(channel_id)

        attendance_model = models.V2ViewerAttendance if v2_channel else models.Attendance
        attendance_channel_id = v2_channel.id if v2_channel else channel_id

        attendance_stats = (await self.db.execute(
            select(
                func.count(attendance_model.id),
                func.coalesce(func.sum(attendance_model.attendance_count), 0),
            )
            .where(attendance_model.channel_id == attendance_channel_id)
        )).one()
        attendance_users, attendance_total = attendance_stats

        if v2_channel:
            notification = (await self.db.execute(
                select(models.V2LiveNotification).where(
                    models.V2LiveNotification.channel_id == v2_channel.id,
                    models.V2LiveNotification.destination_platform == "discord",
                ).limit(1)
            )).scalar_one_or_none()
        else:
            notification = (await self.db.execute(
                select(models.ChzzkNotification).where(models.ChzzkNotification.chzzk_channel_id == channel_id)
            )).scalar_one_or_none()

        commands = sorted(
            await self.chat_service.get_channel_commands(channel_id),
            key=lambda command: command.command,
        )

        greetings = sorted(
            await self.chat_service.get_channel_greetings(channel_id),
            key=lambda greeting: greeting.keyword,
        )

        attendance_rank = (await self.db.execute(
            select(attendance_model)
            .where(attendance_model.channel_id == attendance_channel_id)
            .order_by(attendance_model.attendance_count.desc(), attendance_model.streak_count.desc())
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

    async def save_command(self, channel_id: str, command: str, response: str, cooldown_seconds: int, is_active: bool = True) -> tuple[bool, str | None]:
        status, _ = await self.chat_service.add_chat_command(
            channel_id,
            command,
            response,
            cooldown_seconds,
            is_active,
        )
        if status in ("created", "updated"):
            return True, None
        return False, status

    async def delete_command(self, channel_id: str, command: str) -> bool:
        return await self.chat_service.delete_chat_command(channel_id, command.strip())

    async def save_greeting(self, channel_id: str, keyword: str, response: str) -> tuple[bool, str | None]:
        status, actual_keyword = await self.chat_service.add_greeting(
            channel_id,
            keyword.strip(),
            response.strip(),
        )
        if status in ("created", "updated") and actual_keyword:
            if not await self.redis_service.add_greeting_cache(channel_id, actual_keyword, response.strip()):
                logger.warning("Greeting cache update failed: channel_id=%s keyword=%s", channel_id, actual_keyword)
            return True, None
        return False, status

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
