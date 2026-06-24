import secrets
from enum import Enum

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import PUBLIC_SITE_URL
from app.db import models
from app.features.chat_overlay.schemas import OverlayStyleOptions


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    return int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)


def _rgba(color: str, opacity: int) -> str:
    red, green, blue = _hex_to_rgb(color)
    return f"rgba({red}, {green}, {blue}, {opacity / 100:.2f})"


def build_overlay_css(options: OverlayStyleOptions) -> str:
    justify_map = {
        "top-left": "flex-start",
        "top-right": "flex-start",
        "bottom-left": "flex-end",
        "bottom-right": "flex-end",
        "center": "center",
    }
    align_map = {
        "top-left": "flex-start",
        "bottom-left": "flex-start",
        "top-right": "flex-end",
        "bottom-right": "flex-end",
        "center": "center",
    }
    animation_name = {
        "slide": "message-in-slide",
        "fade": "message-in-fade",
        "pop": "message-in-pop",
        "none": "none",
    }[options.animation]
    animation = "none" if animation_name == "none" else f"{animation_name} 180ms ease-out"
    name_display = "inline" if options.show_name else "none"
    text_shadow = "none"
    box_shadow = "none"
    if options.shadow_strength:
        shadow_alpha = options.shadow_strength / 100
        text_shadow = f"0 1px 2px rgba(0, 0, 0, {shadow_alpha:.2f})"
        box_shadow = f"0 8px 24px rgba(0, 0, 0, {shadow_alpha * 0.35:.2f})"

    background = _rgba(options.background_color, options.background_opacity)
    border = "0"
    if options.bubble_style == "minimal":
        background = "transparent"
        border = f"1px solid {_rgba(options.background_color, min(100, options.background_opacity + 8))}"
        box_shadow = "none"
    elif options.bubble_style == "badge":
        border = f"1px solid {_rgba(options.name_color, 45)}"

    return f"""body {{
    margin: 0;
    overflow: hidden;
    background: transparent;
    font-family: Arial, "Apple SD Gothic Neo", "Malgun Gothic", sans-serif;
}}

.chat-overlay {{
    --overlay-max-messages: {options.max_messages};
    --overlay-message-ttl-ms: {options.message_ttl_seconds * 1000};
    width: 100vw;
    height: 100vh;
    padding: {options.padding}px;
    display: flex;
    flex-direction: column;
    justify-content: {justify_map[options.position]};
    align-items: {align_map[options.position]};
    gap: {options.gap}px;
}}

.chat-message {{
    width: fit-content;
    max-width: min({options.max_width}px, calc(100vw - {options.padding * 2}px));
    padding: {options.message_padding_y}px {options.message_padding_x}px;
    border-radius: {options.radius}px;
    border: {border};
    background: {background};
    color: {options.text_color};
    font-size: {options.font_size}px;
    line-height: 1.35;
    text-shadow: {text_shadow};
    box-shadow: {box_shadow};
    animation: {animation};
}}

.chat-name {{
    display: {name_display};
    margin-right: 8px;
    color: {options.name_color};
    font-weight: 700;
}}

.chat-text {{
    overflow-wrap: anywhere;
}}

@keyframes message-in-slide {{
    from {{
        opacity: 0;
        transform: translateY(10px);
    }}
    to {{
        opacity: 1;
        transform: translateY(0);
    }}
}}

@keyframes message-in-fade {{
    from {{ opacity: 0; }}
    to {{ opacity: 1; }}
}}

@keyframes message-in-pop {{
    from {{
        opacity: 0;
        transform: scale(0.94);
    }}
    to {{
        opacity: 1;
        transform: scale(1);
    }}
}}
"""


DEFAULT_STYLE_OPTIONS = OverlayStyleOptions()
DEFAULT_OVERLAY_CSS = build_overlay_css(DEFAULT_STYLE_OPTIONS)


class PresetDeleteResult(str, Enum):
    DELETED = "deleted"
    CHANNEL_NOT_FOUND = "channel_not_found"
    PRESET_NOT_FOUND = "preset_not_found"


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
                style_mode="options",
                style_options=DEFAULT_STYLE_OPTIONS.model_dump(),
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

    async def get_dashboard_overlay_data(self, platform: str, platform_channel_id: str):
        channel, setting = await self.get_or_create_setting(platform, platform_channel_id)
        if not channel or not setting:
            return None, None, []

        presets = await self.list_presets(channel.id)
        return channel, setting, presets

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

    async def update_setting(
        self,
        platform: str,
        platform_channel_id: str,
        custom_css: str,
        is_active: bool,
        style_mode: str = "options",
        style_options: OverlayStyleOptions | None = None,
    ):
        channel, setting = await self.get_or_create_setting(platform, platform_channel_id)
        if not channel or not setting:
            return None, None

        if style_mode == "custom":
            setting.style_mode = "custom"
            setting.style_options = (style_options or DEFAULT_STYLE_OPTIONS).model_dump()
            setting.custom_css = custom_css
        else:
            options = style_options or DEFAULT_STYLE_OPTIONS
            setting.style_mode = "options"
            setting.style_options = options.model_dump()
            setting.custom_css = build_overlay_css(options)
        setting.is_active = is_active
        await self.db.commit()
        await self.db.refresh(setting)
        return channel, setting

    async def list_presets(self, channel_id):
        result = await self.db.execute(
            select(models.V2ChatOverlayPreset)
            .where(models.V2ChatOverlayPreset.channel_id == channel_id)
            .order_by(models.V2ChatOverlayPreset.updated_at.desc(), models.V2ChatOverlayPreset.name.asc())
        )
        return result.scalars().all()

    async def save_preset(
        self,
        platform: str,
        platform_channel_id: str,
        name: str,
        style_options: OverlayStyleOptions,
        custom_css: str = "",
        style_mode: str = "options",
    ):
        channel, _setting = await self.get_or_create_setting(platform, platform_channel_id)
        if not channel:
            return None

        options_data = style_options.model_dump()
        mode = "custom" if style_mode == "custom" else "options"
        css = custom_css if mode == "custom" else build_overlay_css(style_options)
        result = await self.db.execute(
            select(models.V2ChatOverlayPreset).where(
                models.V2ChatOverlayPreset.channel_id == channel.id,
                models.V2ChatOverlayPreset.name == name,
            )
        )
        preset = result.scalar_one_or_none()
        if preset:
            preset.style_mode = mode
            preset.style_options = options_data
            preset.custom_css = css
        else:
            preset = models.V2ChatOverlayPreset(
                channel_id=channel.id,
                name=name,
                style_mode=mode,
                style_options=options_data,
                custom_css=css,
            )
            self.db.add(preset)

        try:
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            result = await self.db.execute(
                select(models.V2ChatOverlayPreset).where(
                    models.V2ChatOverlayPreset.channel_id == channel.id,
                    models.V2ChatOverlayPreset.name == name,
                )
            )
            preset = result.scalar_one()
            preset.style_mode = mode
            preset.style_options = options_data
            preset.custom_css = css
            await self.db.commit()
        await self.db.refresh(preset)
        return preset

    async def apply_preset(self, platform: str, platform_channel_id: str, preset_id: int):
        channel, setting = await self.get_or_create_setting(platform, platform_channel_id)
        if not channel or not setting:
            return None, None, None

        preset = await self.db.get(models.V2ChatOverlayPreset, preset_id)
        if not preset or preset.channel_id != channel.id:
            return channel, setting, None

        setting.custom_css = preset.custom_css
        setting.style_mode = preset.style_mode
        setting.style_options = preset.style_options
        await self.db.commit()
        await self.db.refresh(setting)
        return channel, setting, preset

    async def delete_preset(self, platform: str, platform_channel_id: str, preset_id: int) -> PresetDeleteResult:
        channel = await self.get_channel(platform, platform_channel_id)
        if not channel:
            return PresetDeleteResult.CHANNEL_NOT_FOUND

        result = await self.db.execute(
            delete(models.V2ChatOverlayPreset).where(
                models.V2ChatOverlayPreset.id == preset_id,
                models.V2ChatOverlayPreset.channel_id == channel.id,
            )
        )
        await self.db.commit()
        return PresetDeleteResult.DELETED if result.rowcount else PresetDeleteResult.PRESET_NOT_FOUND

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
