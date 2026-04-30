from datetime import datetime
from pydantic import BaseModel


class AuthTokenItem(BaseModel):
    channel_id: str
    channel_name: str
    expires_at: datetime
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class AuthListResponse(BaseModel):
    count: int
    items: list[AuthTokenItem]


class TokenRefreshResponse(BaseModel):
    status: str
    new_access_token: str
