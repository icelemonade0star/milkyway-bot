from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class GreetingItem(BaseModel):
    keyword: str
    response: str


class ChannelGreetingCacheResponse(BaseModel):
    channel_id: str
    platform: str | None = None
    platform_channel_id: str | None = None
    channel_uuid: UUID | None = None
    cached: bool
    count: int
    ttl_seconds: int | None = None
    greetings: list[GreetingItem]


class ChannelGreetingSummary(BaseModel):
    channel_id: str
    platform: str | None = None
    platform_channel_id: str | None = None
    channel_uuid: UUID | None = None
    count: int
    ttl_seconds: int | None = None
    greetings: list[GreetingItem]


class AllGreetingCacheResponse(BaseModel):
    total_channels: int
    channels: list[ChannelGreetingSummary]


class GreetingRefreshResponse(BaseModel):
    status: str
    channel_id: str
    platform: str | None = None
    platform_channel_id: str | None = None
    channel_uuid: UUID | None = None
    count: int
    message: str


class FailedChannel(BaseModel):
    channel_id: str
    platform: str | None = None
    platform_channel_id: str | None = None
    channel_uuid: UUID | None = None
    error: str


class AllGreetingRefreshResponse(BaseModel):
    status: str
    refreshed_channels: int
    total_greetings: int
    failed_channels: list[FailedChannel]
    message: str


class LiveStateItem(BaseModel):
    channel_id: UUID
    platform: str
    platform_channel_id: str
    channel_name: str
    is_active: bool
    status: str
    current_stream_session_id: UUID | None = None
    last_checked_at: datetime | None = None
    opened_at: datetime | None = None
    closed_at: datetime | None = None
    stream_title: str | None = None
    category: str | None = None


class LiveStateListResponse(BaseModel):
    total_channels: int
    channels: list[LiveStateItem]


class LiveStateRefreshResponse(BaseModel):
    status: str
    refreshed_channels: int
    message: str
    channel: LiveStateItem | None = None
