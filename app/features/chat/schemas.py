from pydantic import BaseModel


class ChatSendResponse(BaseModel):
    status: str
    message: str


class SessionCreateResponse(BaseModel):
    status: str
    message: str
    channel_id: str


class ActiveSessionsResponse(BaseModel):
    count: int
    channels: list[str]


class MessageResponse(BaseModel):
    status: str
    message: str
