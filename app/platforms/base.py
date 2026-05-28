from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol


@dataclass(slots=True)
class PlatformIdentity:
    platform: str
    platform_channel_id: str
    channel_name: str
    profile_image_url: str | None = None


@dataclass(slots=True)
class TokenBundle:
    access_token: str
    refresh_token: str | None
    expires_at: datetime | None
    token_type: str | None = None
    scope: str | None = None
    raw: dict[str, Any] | None = None


@dataclass(slots=True)
class LiveStatus:
    platform: str
    platform_channel_id: str
    status: str
    opened_at: datetime | None = None
    closed_at: datetime | None = None
    title: str | None = None
    category: str | None = None
    thumbnail_url: str | None = None
    raw: dict[str, Any] | None = None


class AuthProvider(Protocol):
    platform: str

    def get_auth_url(self, state: str | None = None) -> tuple[str, str]:
        ...

    async def exchange_code_for_token(self, code: str, state: str) -> TokenBundle | None:
        ...

    async def get_identity(self, access_token: str | None = None) -> PlatformIdentity | None:
        ...

    async def refresh_access_token(self, platform_channel_id: str) -> tuple[str | None, int | None]:
        ...


class LiveProvider(Protocol):
    platform: str

    async def get_channel_info(self, platform_channel_id: str) -> dict[str, Any] | None:
        ...

    async def get_live_status(self, platform_channel_id: str) -> LiveStatus | None:
        ...

    def get_live_url(self, platform_channel_id: str) -> str:
        ...

    async def close(self) -> None:
        ...


class ChatSession(Protocol):
    channel_id: str

    async def create_session(self):
        ...

    async def subscribe_chat(self):
        ...

    async def send_chat(self, message: str):
        ...
