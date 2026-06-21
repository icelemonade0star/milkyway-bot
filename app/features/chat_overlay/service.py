import secrets

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import PUBLIC_SITE_URL
from app.db import models


DEFAULT_OVERLAY_CSS = """body {
    margin: 0;
    overflow: hidden;
    background: transparent;
    font-family: Arial, "Apple SD Gothic Neo", "Malgun Gothic", sans-serif;
}

.chat-overlay {
    width: 100vw;
    height: 100vh;
    padding: 20px;
    display: flex;
    flex-direction: column;
    justify-content: flex-end;
    gap: 8px;
}

.chat-message {
    width: fit-content;
    max-width: min(760px, calc(100vw - 40px));
    padding: 8px 12px;
    border-radius: 8px;
    background: rgba(22, 24, 29, 0.78);
    color: #ffffff;
    font-size: 20px;
    line-height: 1.35;
    text-shadow: 0 1px 2px rgba(0, 0, 0, 0.45);
    animation: message-in 180ms ease-out;
}

.chat-name {
    margin-right: 8px;
    color: #7ee2a8;
    font-weight: 700;
}

.chat-text {
    overflow-wrap: anywhere;
}

@keyframes message-in {
    from {
        opacity: 0;
        transform: translateY(10px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}
"""


class ChatOverlayService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_channel(self, platform: str, platform_channel_id: str):
        result = await self.db.execute(
            select(models.V2Channel).where(
                models.V2Channel.platform == platform,
                models.V2Channel.platform_channel_id == platform_channel_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_or_create_setting(self, platform: str, platform_channel_id: str):
        channel = await self.get_channel(platform, platform_channel_id)
        if not channel:
            return None, None

        setting = await self.db.get(models.V2ChatOverlaySetting, channel.id)
        if not setting:
            setting = models.V2ChatOverlaySetting(
                channel_id=channel.id,
                public_token=secrets.token_urlsafe(32),
                custom_css=DEFAULT_OVERLAY_CSS,
                is_active=True,
            )
            self.db.add(setting)
            try:
                await self.db.commit()
                await self.db.refresh(setting)
            except IntegrityError:
                await self.db.rollback()
                setting = await self.db.get(models.V2ChatOverlaySetting, channel.id)
                if not setting:
                    raise

        return channel, setting

    async def get_setting_by_token(self, token: str):
        result = await self.db.execute(
            select(models.V2Channel, models.V2ChatOverlaySetting)
            .join(
                models.V2ChatOverlaySetting,
                models.V2ChatOverlaySetting.channel_id == models.V2Channel.id,
            )
            .where(models.V2ChatOverlaySetting.public_token == token)
        )
        return result.one_or_none()

    async def update_setting(self, platform: str, platform_channel_id: str, custom_css: str, is_active: bool):
        channel, setting = await self.get_or_create_setting(platform, platform_channel_id)
        if not channel or not setting:
            return None, None

        setting.custom_css = custom_css
        setting.is_active = is_active
        await self.db.commit()
        await self.db.refresh(setting)
        return channel, setting

    async def rotate_token(self, platform: str, platform_channel_id: str):
        channel, setting = await self.get_or_create_setting(platform, platform_channel_id)
        if not channel or not setting:
            return None, None

        setting.public_token = secrets.token_urlsafe(32)
        await self.db.commit()
        await self.db.refresh(setting)
        return channel, setting

    @staticmethod
    def overlay_url(token: str) -> str:
        return f"{PUBLIC_SITE_URL}/overlay/chat/{token}"
