import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models
from app.features.chat.handling.helpers import CHAT_PLATFORM
from app.features.discord_bot.cogs.chzzk_notifications import invalidate_notification_cache
from app.features.discord_bot.cogs.discord_service import DiscordService

logger = logging.getLogger("MessageHandling")


async def handle_set_notification(session, db: AsyncSession, channel_id: str, args: list, user_name: str):
    if len(args) < 1:
        await session.send_chat("사용법: 우선, !디스코드봇으로 나온 url로 디스코드에 봇을 초대해주세요. 그리고 채팅창에 !알림설정 [디스코드채널ID]를 입력하세요.")
        return

    discord_channel_id = args[0]

    discord_service = DiscordService()
    test_msg = f"🔔 [MilkywayBot] '{user_name}'님의 방송 알림이 이 채널로 정상적으로 설정되었습니다."

    if not await discord_service.send_message(discord_channel_id, test_msg):
        await session.send_chat(f"❌ 설정 실패: 디스코드 채널({discord_channel_id})에 테스트 메시지를 보낼 수 없습니다. 봇이 초대되었는지, 채널 ID가 맞는지 확인해주세요.")
        return

    try:
        v2_channel = (await db.execute(
            select(models.V2Channel).where(
                models.V2Channel.platform == CHAT_PLATFORM,
                models.V2Channel.platform_channel_id == channel_id,
            )
        )).scalar_one_or_none()

        if not v2_channel:
            await session.send_chat("알림 설정 실패: v2 채널 정보를 찾을 수 없습니다.")
            return

        existing = (await db.execute(
            select(models.V2LiveNotification).where(
                models.V2LiveNotification.channel_id == v2_channel.id,
                models.V2LiveNotification.destination_platform == "discord",
            ).limit(1)
        )).scalar_one_or_none()

        if existing:
            existing.destination_channel_id = discord_channel_id
            existing.mention_role = existing.mention_role or "@everyone"
            existing.is_active = True
        else:
            db.add(models.V2LiveNotification(
                channel_id=v2_channel.id,
                destination_platform="discord",
                destination_channel_id=discord_channel_id,
                mention_role="@everyone",
                is_active=True,
            ))

        await db.commit()
        invalidate_notification_cache()
        verb = "업데이트" if existing else "등록"
        await session.send_chat(f"알림 설정이 {verb}되었습니다. (Discord ID: {discord_channel_id})")

    except Exception as e:
        await db.rollback()
        logger.error("알림 설정 저장 실패: %s", e)
        await session.send_chat("알림 설정 중 오류가 발생했습니다.")


async def handle_delete_notification(session, db: AsyncSession, channel_id: str):
    v2_channel = (await db.execute(
        select(models.V2Channel).where(
            models.V2Channel.platform == CHAT_PLATFORM,
            models.V2Channel.platform_channel_id == channel_id,
        )
    )).scalar_one_or_none()

    if not v2_channel:
        await session.send_chat("활성화된 알림 설정이 없습니다.")
        return

    notifications = (await db.execute(
        select(models.V2LiveNotification).where(
            models.V2LiveNotification.channel_id == v2_channel.id,
            models.V2LiveNotification.destination_platform == "discord",
            models.V2LiveNotification.is_active == True,
        )
    )).scalars().all()

    if not notifications:
        await session.send_chat("활성화된 알림 설정이 없습니다.")
        return

    for notification in notifications:
        notification.is_active = False

    await db.commit()
    invalidate_notification_cache()
    await session.send_chat("알림 설정이 해제되었습니다.")
