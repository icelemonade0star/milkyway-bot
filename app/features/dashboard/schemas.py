from pydantic import BaseModel, Field


class CommandSaveRequest(BaseModel):
    command: str = Field(min_length=1, max_length=100)
    response: str = Field(min_length=1)
    cooldown_seconds: int = Field(default=5, ge=0, le=86400)


class GreetingSaveRequest(BaseModel):
    keyword: str = Field(min_length=1, max_length=100)
    response: str = Field(min_length=1)


class DeleteRequest(BaseModel):
    key: str = Field(min_length=1, max_length=100)
