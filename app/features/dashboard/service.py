import logging
import json

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models
from app.features.auth.service import AuthService
from app.features.chat.service import ChatService
from app.redis.redis_service import RedisConfigService

logger = logging.getLogger("DashboardService")


def parse_attendance_response(response: str | None) -> dict[str, str]:
    parsed = {
        "checked": "",
        "already_checked": "",
        "not_streaming": "",
    }
    if not response:
        return parsed

    try:
        payload = json.loads(response)
    except (TypeError, json.JSONDecodeError):
        parsed["checked"] = response
        return parsed

    if not isinstance(payload, dict):
        return parsed

    for key in parsed:
        value = payload.get(key)
        if isinstance(value, str):
            parsed[key] = value
    return parsed


class DashboardService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.chat_service = ChatService(db)
        self.redis_service = RedisConfigService()

    async def get_dashboard_data(self, platform: str, channel_id: str):
        auth_service = AuthService(self.db)
        auth_token = await auth_service.get_auth_token_by_id(platform, channel_id)
        if not auth_token:
            return None
        v2_channel = await auth_service.get_v2_channel_by_platform_id(platform, channel_id)

        config = await self.chat_service.get_channel_config(channel_id, platform)

        if not v2_channel:
            return None

        attendance_model = models.V2ViewerAttendance
        attendance_channel_id = v2_channel.id

        attendance_stats = (await self.db.execute(
            select(
                func.count(attendance_model.id),
                func.coalesce(func.sum(attendance_model.attendance_count), 0),
            )
            .where(attendance_model.channel_id == attendance_channel_id)
        )).one()
        attendance_users, attendance_total = attendance_stats

        notification = (await self.db.execute(
            select(models.V2LiveNotification).where(
                models.V2LiveNotification.channel_id == v2_channel.id,
                models.V2LiveNotification.destination_platform == "discord",
            ).limit(1)
        )).scalar_one_or_none()

        all_commands = sorted(
            await self.chat_service.get_channel_commands(channel_id, platform),
            key=lambda command: command.command,
        )
        commands = [command for command in all_commands if command.type != "attendance"]
        attendance_commands = [command for command in all_commands if command.type == "attendance"]
        attendance_command = attendance_commands[0] if attendance_commands else None

        greetings = sorted(
            await self.chat_service.get_channel_greetings(channel_id, platform),
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
            "attendance_command": attendance_command,
            "attendance_responses": parse_attendance_response(attendance_command.response if attendance_command else None),
            "greetings": greetings,
            "attendance_rank": attendance_rank,
            "stats": {
                "attendance_users": attendance_users,
                "attendance_total": attendance_total,
            },
        }

    async def save_command(self, platform: str, channel_id: str, command: str, response: str, cooldown_seconds: int, is_active: bool = True, command_type: str = "text") -> tuple[bool, str | None]:
        status, _ = await self.chat_service.add_chat_command(
            channel_id,
            command,
            response,
            platform,
            cooldown_seconds,
            is_active,
            command_type,
        )
        if status in ("created", "updated"):
            return True, None
        return False, status

    async def delete_command(self, platform: str, channel_id: str, command: str) -> bool:
        return await self.chat_service.delete_chat_command(channel_id, command.strip(), platform)

    async def save_greeting(self, platform: str, channel_id: str, keyword: str, response: str) -> tuple[bool, str | None]:
        status, actual_keyword = await self.chat_service.add_greeting(
            channel_id,
            keyword.strip(),
            response.strip(),
            platform,
        )
        if status in ("created", "updated") and actual_keyword:
            await self.redis_service.refresh_greetings_cache(channel_id, platform)
            return True, None
        return False, status

    async def delete_greeting(self, platform: str, channel_id: str, keyword: str) -> bool:
        target = await self.chat_service.get_greeting(channel_id, keyword.strip(), platform)
        if not target:
            return False

        actual_keyword = target.keyword
        try:
            await self.db.delete(target)
            await self.db.commit()
        except Exception as e:
            await self.db.rollback()
            logger.warning("대시보드 인사말 삭제 실패: %s", e)
            return False

        await self.redis_service.refresh_greetings_cache(channel_id, platform)
        return True
