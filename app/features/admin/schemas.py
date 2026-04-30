from pydantic import BaseModel


class GreetingItem(BaseModel):
    keyword: str
    response: str


class ChannelGreetingCacheResponse(BaseModel):
    channel_id: str
    cached: bool
    count: int
    ttl_seconds: int | None = None
    greetings: list[GreetingItem]


class ChannelGreetingSummary(BaseModel):
    channel_id: str
    count: int
    ttl_seconds: int | None = None
    greetings: list[GreetingItem]


class AllGreetingCacheResponse(BaseModel):
    total_channels: int
    channels: list[ChannelGreetingSummary]


class GreetingRefreshResponse(BaseModel):
    status: str
    channel_id: str
    count: int
    message: str


class FailedChannel(BaseModel):
    channel_id: str
    error: str


class AllGreetingRefreshResponse(BaseModel):
    status: str
    refreshed_channels: int
    total_greetings: int
    failed_channels: list[FailedChannel]
    message: str
