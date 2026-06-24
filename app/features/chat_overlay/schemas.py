from typing import Literal

from pydantic import BaseModel, Field, field_validator


HEX_COLOR_PATTERN = r"^#[0-9a-fA-F]{6}$"


class OverlayStyleOptions(BaseModel):
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
    shadow_strength: int = Field(default=45, ge=0, le=100)
    animation: Literal["slide", "fade", "pop", "none"] = "slide"
    show_name: bool = True
    bubble_style: Literal["solid", "minimal", "badge"] = "solid"
    message_ttl_seconds: int = Field(default=16, ge=3, le=3600)
    blocked_nicknames: list[str] = Field(default_factory=list, max_length=200)
    blocked_roles: list[str] = Field(default_factory=list, max_length=20)

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


class OverlaySaveRequest(BaseModel):
    custom_css: str = Field(default="", max_length=12000)
    is_active: bool = True
    style_mode: Literal["options", "custom"] = "options"
    style_options: OverlayStyleOptions | None = None

    @field_validator("custom_css")
    @classmethod
    def validate_custom_css(cls, value: str) -> str:
        lowered = value.lower()
        if "</style" in lowered or "<script" in lowered:
            raise ValueError("CSS만 입력할 수 있습니다.")
        if "@import" in lowered or "javascript:" in lowered:
            raise ValueError("외부 CSS import나 스크립트 URL은 사용할 수 없습니다.")
        return value


class OverlayPresetSaveRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    custom_css: str = Field(default="", max_length=12000)
    style_mode: Literal["options", "custom"] = "options"
    style_options: OverlayStyleOptions

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("프리셋 이름을 입력해 주세요.")
        return value

    @field_validator("custom_css")
    @classmethod
    def validate_custom_css(cls, value: str) -> str:
        return OverlaySaveRequest.validate_custom_css(value)
