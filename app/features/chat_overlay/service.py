from dataclasses import dataclass
from enum import Enum
from typing import Callable

from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import PUBLIC_SITE_URL
from app.db import models
from app.features.chat_overlay.schemas import ChatOverlayStyleOptions, TimerOverlayStyleOptions


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    return int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)


def _rgba(color: str, opacity: int) -> str:
    red, green, blue = _hex_to_rgb(color)
    return f"rgba({red}, {green}, {blue}, {opacity / 100:.2f})"


def build_overlay_css(options: ChatOverlayStyleOptions) -> str:
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
    if options.name_mode == "inline":
        name_display = "inline"
        name_margin_right = 8
        name_margin_bottom = 0
    elif options.name_mode == "wrap":
        name_display = "block"
        name_margin_right = 0
        name_margin_bottom = 2
    elif options.name_mode == "hidden":
        name_display = "none"
        name_margin_right = 0
        name_margin_bottom = 0
    else:  # separate
        name_display = "block"
        name_margin_right = 0
        name_margin_bottom = 0
    grid_align = {
        "top-left": "start", "top-right": "start",
        "bottom-left": "end", "bottom-right": "end", "center": "center",
    }.get(options.position, "end")
    grid_justify = {
        "top-left": "start", "bottom-left": "start",
        "top-right": "end", "bottom-right": "end", "center": "center",
    }.get(options.position, "start")
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

    return f"""/* 오버레이 캔버스: OBS 브라우저 소스의 기본 영역입니다. */
body {{
    margin: 0;
    overflow: hidden;
    background: transparent;
    font-family: Arial, "Apple SD Gothic Neo", "Malgun Gothic", sans-serif;
}}

/* padding이 OBS 화면 밖으로 밀리지 않도록 전체 박스 계산을 고정합니다. */
*, *::before, *::after {{
    box-sizing: border-box;
}}

html, body {{
    width: 100%;
    height: 100%;
}}

/*
전체 오버레이 영역입니다.
- 채팅 묶음의 위치, 화면 여백, 메시지 간격을 조절합니다.
- --overlay-message-ttl-ms는 JS가 메시지 유지 시간을 읽는 값입니다.
*/
.chat-overlay {{
    --overlay-message-ttl-ms: {options.message_ttl_seconds * 1000};
    --overlay-name-color-mode: {options.name_color_mode};
    --overlay-name-color-palette: {",".join(options.name_color_palette)};
    width: 100%;
    height: 100%;
    padding: {options.padding}px;
    display: flex;
    flex-direction: column;
    justify-content: {justify_map[options.position]};
    align-items: {align_map[options.position]};
    gap: {options.gap}px;
}}

/*
채팅창 프레임/배경 스킨 영역입니다.
- 전체 채팅창 이미지, 테두리, 장식 배경을 넣을 때 사용합니다.
- 예: background: url("frame.png") center / contain no-repeat;
*/
.chat-frame {{
    width: 100%;
    height: 100%;
    min-width: 0;
    min-height: 0;
    display: flex;
    flex-direction: column;
    justify-content: inherit;
    align-items: inherit;
    gap: inherit;
}}

/*
메시지 목록 영역입니다.
- 프레임 이미지 안쪽 여백, 메시지가 보이는 범위, 클리핑을 조절합니다.
- 예: padding: 48px 36px 32px;
*/
.chat-list {{
    width: 100%;
    height: 100%;
    min-width: 0;
    min-height: 0;
    display: flex;
    flex-direction: column;
    justify-content: inherit;
    align-items: inherit;
    gap: inherit;
    overflow: hidden;
}}

/*
개별 채팅 말풍선입니다.
- 말풍선 이미지나 메시지 배경을 넣을 때 사용합니다.
- 예: background: url("bubble.png") center / 100% 100% no-repeat;
*/
{f'''.chat-list {{
    display: grid;
    max-width: min({options.max_width}px, 100%);
    grid-template-columns: auto 1fr;
    align-content: {grid_align};
    justify-content: {grid_justify};
    row-gap: {options.gap}px;
    column-gap: {options.name_gap}px;
    font-size: {options.font_size}px;
    line-height: 1.35;
}}

.chat-message {{
    display: contents;
}}

.chat-name {{
    align-self: start;
    padding-top: {options.message_padding_y}px;
    color: {options.name_color};
    font-weight: 700;
    text-shadow: {text_shadow};
    overflow-wrap: anywhere;
    word-break: break-word;
    animation: {animation};
}}

.chat-text {{
    min-width: 0;
    padding: {options.message_padding_y}px {options.message_padding_x}px;
    border-radius: {options.radius}px;
    border: {border};
    background: {background};
    color: {options.text_color};
    text-shadow: {text_shadow};
    box-shadow: {box_shadow};
    overflow-wrap: anywhere;
    word-break: break-word;
    animation: {animation};
}}''' if options.name_mode == "separate" else f'''.chat-message {{
    width: fit-content;
    max-width: min({options.max_width}px, 100%);
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
    overflow-wrap: anywhere;
}}

/* 말풍선 안의 닉네임 텍스트입니다. */
.chat-name {{
    display: {name_display};
    margin-right: {name_margin_right}px;
    margin-bottom: {name_margin_bottom}px;
    color: {options.name_color};
    font-weight: 700;
}}

/* 말풍선 안의 채팅 본문입니다. */
.chat-text {{
    min-width: 0;
    overflow-wrap: anywhere;
    word-break: break-word;
}}'''}

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


def build_timer_overlay_css(options: TimerOverlayStyleOptions) -> str:
    """채팅 오버레이와 완전히 독립된 타이머 오버레이 전용 CSS입니다."""
    timer_background = _rgba(options.timer_background_color, options.timer_background_opacity)
    timer_title_display = "none" if options.timer_display_mode == "simple" else "block"
    timer_font_size = 96 if options.timer_display_mode == "simple" else options.timer_font_size

    return f"""body {{
    display: flex;
    align-items: center;
    justify-content: center;
}}

.timer-overlay {{
    min-width: min(520px, 100%);
    padding: 18px 22px;
    display: none;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 6px;
    border-radius: 8px;
    background: {timer_background};
    opacity: {options.timer_global_opacity / 100:.2f};
    font-family: "Pretendard", "Apple SD Gothic Neo", "Malgun Gothic", sans-serif;
    text-shadow: 0 2px 16px rgba(0, 0, 0, 0.4);
}}

.timer-overlay.is-visible {{
    display: flex;
}}

.timer-title {{
    display: {timer_title_display};
    color: {options.timer_title_color};
    font-size: 18px;
    font-weight: 500;
    opacity: 0.85;
    overflow-wrap: anywhere;
    letter-spacing: 0;
}}

.timer-time {{
    color: {options.timer_text_color};
    font-size: {timer_font_size}px;
    font-weight: {options.timer_font_weight};
    line-height: 1;
    font-variant-numeric: tabular-nums;
    letter-spacing: 0;
}}

.timer-overlay.is-done .timer-time {{
    color: {options.timer_done_color};
    animation: timer-pulse 1s ease-in-out infinite;
}}

@keyframes timer-pulse {{
    0%, 100% {{ opacity: 1; }}
    50% {{ opacity: 0.5; }}
}}
"""


@dataclass(frozen=True)
class OverlayKindConfig:
    style_options_cls: type[BaseModel]
    default_options: BaseModel
    build_css: Callable[[BaseModel], str]


DEFAULT_CHAT_STYLE_OPTIONS = ChatOverlayStyleOptions()
DEFAULT_TIMER_STYLE_OPTIONS = TimerOverlayStyleOptions()
DEFAULT_OVERLAY_CSS = build_overlay_css(DEFAULT_CHAT_STYLE_OPTIONS)
DEFAULT_TIMER_OVERLAY_CSS = build_timer_overlay_css(DEFAULT_TIMER_STYLE_OPTIONS)

OVERLAY_KIND_CONFIG: dict[str, OverlayKindConfig] = {
    "chat": OverlayKindConfig(ChatOverlayStyleOptions, DEFAULT_CHAT_STYLE_OPTIONS, build_overlay_css),
    "timer": OverlayKindConfig(TimerOverlayStyleOptions, DEFAULT_TIMER_STYLE_OPTIONS, build_timer_overlay_css),
}


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

    async def get_or_create_setting(self, platform: str, platform_channel_id: str, overlay_kind: str = "chat"):
        channel = await self.get_channel(platform, platform_channel_id)
        if not channel:
            return None, None

        setting = await self.db.get(models.V2OverlaySetting, (channel.id, overlay_kind))
        if not setting:
            config = OVERLAY_KIND_CONFIG[overlay_kind]
            setting = models.V2OverlaySetting(
                channel_id=channel.id,
                overlay_kind=overlay_kind,
                style_mode="options",
                style_options=config.default_options.model_dump(),
                custom_css=config.build_css(config.default_options),
                is_active=True,
            )
            self.db.add(setting)
            try:
                await self.db.commit()
                await self.db.refresh(setting)
            except IntegrityError:
                await self.db.rollback()
                setting = await self.db.get(models.V2OverlaySetting, (channel.id, overlay_kind))
                if not setting:
                    raise

        return channel, setting

    async def get_dashboard_overlay_data(self, platform: str, platform_channel_id: str):
        """타이머는 프리셋을 지원하지 않으므로 프리셋은 채팅용만 반환합니다."""
        channel, chat_setting = await self.get_or_create_setting(platform, platform_channel_id, "chat")
        if not channel or not chat_setting:
            return None, {}, []

        _channel, timer_setting = await self.get_or_create_setting(platform, platform_channel_id, "timer")
        settings_by_kind = {"chat": chat_setting, "timer": timer_setting}
        presets = await self.list_presets(channel.id, "chat")
        return channel, settings_by_kind, presets

    async def get_setting_by_channel(self, platform: str, platform_channel_id: str, overlay_kind: str = "chat"):
        channel, setting = await self.get_or_create_setting(platform, platform_channel_id, overlay_kind)
        if not channel or not setting:
            return None
        return channel, setting

    async def get_preset_by_name(self, platform: str, platform_channel_id: str, preset_name: str, overlay_kind: str = "chat"):
        channel = await self.get_channel(platform, platform_channel_id)
        if not channel:
            return None
        result = await self.db.execute(
            select(models.V2OverlayPreset).where(
                models.V2OverlayPreset.channel_id == channel.id,
                models.V2OverlayPreset.overlay_kind == overlay_kind,
                models.V2OverlayPreset.name == preset_name,
            )
        )
        return result.scalar_one_or_none()

    async def update_setting(
        self,
        platform: str,
        platform_channel_id: str,
        overlay_kind: str,
        custom_css: str,
        is_active: bool,
        style_mode: str = "options",
        style_options: BaseModel | None = None,
    ):
        channel, setting = await self.get_or_create_setting(platform, platform_channel_id, overlay_kind)
        if not channel or not setting:
            return None, None

        config = OVERLAY_KIND_CONFIG[overlay_kind]
        options = style_options or config.default_options
        if style_mode == "custom":
            setting.style_mode = "custom"
            setting.style_options = options.model_dump()
            setting.custom_css = custom_css
        else:
            setting.style_mode = "options"
            setting.style_options = options.model_dump()
            setting.custom_css = config.build_css(options)
        setting.is_active = is_active
        await self.db.commit()
        await self.db.refresh(setting)
        return channel, setting

    async def list_presets(self, channel_id, overlay_kind: str = "chat"):
        result = await self.db.execute(
            select(models.V2OverlayPreset)
            .where(models.V2OverlayPreset.channel_id == channel_id, models.V2OverlayPreset.overlay_kind == overlay_kind)
            .order_by(models.V2OverlayPreset.updated_at.desc(), models.V2OverlayPreset.name.asc())
        )
        return result.scalars().all()

    async def save_preset(
        self,
        platform: str,
        platform_channel_id: str,
        overlay_kind: str,
        name: str,
        style_options: BaseModel,
        custom_css: str = "",
        style_mode: str = "options",
    ):
        channel, _setting = await self.get_or_create_setting(platform, platform_channel_id, overlay_kind)
        if not channel:
            return None

        config = OVERLAY_KIND_CONFIG[overlay_kind]
        options_data = style_options.model_dump()
        mode = "custom" if style_mode == "custom" else "options"
        css = custom_css if mode == "custom" else config.build_css(style_options)
        result = await self.db.execute(
            select(models.V2OverlayPreset).where(
                models.V2OverlayPreset.channel_id == channel.id,
                models.V2OverlayPreset.overlay_kind == overlay_kind,
                models.V2OverlayPreset.name == name,
            )
        )
        preset = result.scalar_one_or_none()
        if preset:
            preset.style_mode = mode
            preset.style_options = options_data
            preset.custom_css = css
        else:
            preset = models.V2OverlayPreset(
                channel_id=channel.id,
                overlay_kind=overlay_kind,
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
                select(models.V2OverlayPreset).where(
                    models.V2OverlayPreset.channel_id == channel.id,
                    models.V2OverlayPreset.overlay_kind == overlay_kind,
                    models.V2OverlayPreset.name == name,
                )
            )
            preset = result.scalar_one()
            preset.style_mode = mode
            preset.style_options = options_data
            preset.custom_css = css
            await self.db.commit()
        await self.db.refresh(preset)
        return preset

    async def apply_preset(self, platform: str, platform_channel_id: str, overlay_kind: str, preset_id: int):
        channel, setting = await self.get_or_create_setting(platform, platform_channel_id, overlay_kind)
        if not channel or not setting:
            return None, None, None

        preset = await self.db.get(models.V2OverlayPreset, preset_id)
        if not preset or preset.channel_id != channel.id or preset.overlay_kind != overlay_kind:
            return channel, setting, None

        setting.custom_css = preset.custom_css
        setting.style_mode = preset.style_mode
        setting.style_options = preset.style_options
        await self.db.commit()
        await self.db.refresh(setting)
        return channel, setting, preset

    async def delete_preset(self, platform: str, platform_channel_id: str, overlay_kind: str, preset_id: int) -> PresetDeleteResult:
        channel = await self.get_channel(platform, platform_channel_id)
        if not channel:
            return PresetDeleteResult.CHANNEL_NOT_FOUND

        result = await self.db.execute(
            delete(models.V2OverlayPreset).where(
                models.V2OverlayPreset.id == preset_id,
                models.V2OverlayPreset.channel_id == channel.id,
                models.V2OverlayPreset.overlay_kind == overlay_kind,
            )
        )
        await self.db.commit()
        return PresetDeleteResult.DELETED if result.rowcount else PresetDeleteResult.PRESET_NOT_FOUND

    @staticmethod
    def overlay_url(platform: str, platform_channel_id: str) -> str:
        return f"{PUBLIC_SITE_URL}/overlay/chat/{platform}/{platform_channel_id}"

    @staticmethod
    def timer_overlay_url(platform: str, platform_channel_id: str) -> str:
        return f"{PUBLIC_SITE_URL}/overlay/timer/{platform}/{platform_channel_id}"
