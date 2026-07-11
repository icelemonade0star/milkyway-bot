import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


HEX_COLOR_PATTERN = r"^#[0-9a-fA-F]{6}$"


def _validate_css_snippet(value: str) -> str:
    lowered = value.lower()
    if "</style" in lowered or "<script" in lowered:
        raise ValueError("CSS만 입력할 수 있습니다.")
    if "@import" in lowered or "javascript:" in lowered:
        raise ValueError("외부 CSS import나 스크립트 URL은 사용할 수 없습니다.")
    return value


class ChatOverlayStyleOptions(BaseModel):
    position: Literal["bottom-left", "bottom-right", "top-left", "top-right", "center"] = "bottom-left"
    font_size: int = Field(default=20, ge=12, le=48)
    max_width: int = Field(default=760, ge=260, le=1400)
    gap: int = Field(default=8, ge=0, le=32)
    padding: int = Field(default=20, ge=0, le=80)
    message_padding_y: int = Field(default=8, ge=0, le=28)
    message_padding_x: int = Field(default=12, ge=4, le=40)
    radius: int = Field(default=8, ge=0, le=40)
    background_color: str = Field(default="#16181d", pattern=HEX_COLOR_PATTERN)
    background_opacity: int = Field(default=78, ge=0, le=100)
    text_color: str = Field(default="#ffffff", pattern=HEX_COLOR_PATTERN)
    name_color: str = Field(default="#7ee2a8", pattern=HEX_COLOR_PATTERN)
    name_color_mode: Literal["fixed", "random"] = "fixed"
    name_color_palette: list[str] = Field(
        default_factory=lambda: ["#7ee2a8", "#7ac7ff", "#ffd166", "#ff8fab", "#c4a7ff"],
        max_length=20,
    )
    shadow_strength: int = Field(default=45, ge=0, le=100)
    animation: Literal["slide", "fade", "pop", "none"] = "slide"
    name_mode: Literal["inline", "wrap", "separate", "hidden"] = "inline"
    name_gap: int = Field(default=4, ge=0, le=40)
    bubble_style: Literal["solid", "minimal", "badge"] = "solid"
    message_ttl_seconds: int = Field(default=60, ge=3, le=3600)
    blocked_nicknames: list[str] = Field(default_factory=list, max_length=200)
    blocked_roles: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_name_fields(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        if "name_mode" not in data:
            show_name = data.pop("show_name", True)
            name_wrap = data.pop("name_wrap", False)
            if not show_name:
                data["name_mode"] = "hidden"
            elif name_wrap:
                data["name_mode"] = "wrap"
            else:
                data["name_mode"] = "inline"
        else:
            data.pop("show_name", None)
            data.pop("name_wrap", None)
        return data

    @field_validator("blocked_nicknames")
    @classmethod
    def normalize_filter_values(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            item = value.strip()
            if not item or item in seen:
                continue
            if len(item) > 255:
                raise ValueError("필터 항목은 255자 이하여야 합니다.")
            normalized.append(item)
            seen.add(item)
        return normalized

    @field_validator("name_color_palette")
    @classmethod
    def normalize_name_color_palette(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            color = value.strip()
            if not color or color in seen:
                continue
            if not re.fullmatch(HEX_COLOR_PATTERN, color):
                raise ValueError("닉네임 색상 목록은 #RRGGBB 형식이어야 합니다.")
            normalized.append(color)
            seen.add(color)
        return normalized or ["#7ee2a8"]

    @field_validator("blocked_roles")
    @classmethod
    def normalize_roles(cls, values: list[str]) -> list[str]:
        allowed_roles = {"streamer", "manager"}
        normalized: list[str] = []
        for value in values:
            item = value.strip().casefold()
            if not item or item not in allowed_roles or item in normalized:
                continue
            normalized.append(item)
        return normalized


class TimerOverlayStyleOptions(BaseModel):
    timer_autoplay: bool = True
    timer_auto_delete: bool = False
    timer_auto_delete_delay_seconds: int = Field(default=5, ge=0, le=3600)
    timer_display_mode: Literal["simple", "titled"] = "titled"
    timer_title_text: str = Field(default="타이머", max_length=40)
    timer_font_size: int = Field(default=72, ge=32, le=160)
    timer_font_weight: Literal["400", "600", "700", "900"] = "700"
    timer_text_color: str = Field(default="#ffffff", pattern=HEX_COLOR_PATTERN)
    timer_title_color: str = Field(default="#cccccc", pattern=HEX_COLOR_PATTERN)
    timer_done_color: str = Field(default="#ff8fab", pattern=HEX_COLOR_PATTERN)
    timer_background_color: str = Field(default="#1a1a2a", pattern=HEX_COLOR_PATTERN)
    timer_background_opacity: int = Field(default=100, ge=0, le=100)
    timer_global_opacity: int = Field(default=100, ge=0, le=100)

    @field_validator("timer_title_text")
    @classmethod
    def normalize_timer_title_text(cls, value: str) -> str:
        return value.strip() or "타이머"


class _CssSnippetMixin(BaseModel):
    @field_validator("custom_css", check_fields=False)
    @classmethod
    def validate_custom_css(cls, value: str) -> str:
        return _validate_css_snippet(value)


class _PresetNameMixin(BaseModel):
    @field_validator("name", check_fields=False)
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("프리셋 이름을 입력해 주세요.")
        return value


class ChatOverlaySaveRequest(_CssSnippetMixin):
    custom_css: str = Field(default="", max_length=12000)
    is_active: bool = True
    style_mode: Literal["options", "custom"] = "options"
    style_options: ChatOverlayStyleOptions | None = None


class TimerOverlaySaveRequest(_CssSnippetMixin):
    custom_css: str = Field(default="", max_length=12000)
    is_active: bool = True
    style_mode: Literal["options", "custom"] = "options"
    style_options: TimerOverlayStyleOptions | None = None


class ChatOverlayPresetSaveRequest(_CssSnippetMixin, _PresetNameMixin):
    name: str = Field(min_length=1, max_length=80)
    custom_css: str = Field(default="", max_length=12000)
    style_mode: Literal["options", "custom"] = "options"
    style_options: ChatOverlayStyleOptions
