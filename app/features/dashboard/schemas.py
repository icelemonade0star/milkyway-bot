import json
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.config import MAX_CHAT_RESPONSE_CHARS


def normalize_trigger(value: str, label: str) -> str:
    parts = [part.strip() for part in value.strip().split("|")]
    if not parts or any(not part for part in parts):
        raise ValueError(f"{label}을 입력해주세요.")
    if any(any(char.isspace() for char in part) for part in parts):
        raise ValueError(f"{label}에는 공백을 사용할 수 없습니다.")
    return "|".join(parts)


def normalize_required_text(value: str, label: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError(f"{label}을 입력해주세요.")
    return value


class CommandSaveRequest(BaseModel):
    command: str = Field(min_length=1, max_length=100)
    response: str = Field(min_length=1)
    type: Literal["text", "attendance"] = "text"
    cooldown_seconds: int = Field(default=5, ge=0, le=86400)
    is_active: bool = True

    @field_validator("command")
    @classmethod
    def validate_command(cls, value: str) -> str:
        return normalize_trigger(value, "명령어")

    @field_validator("response")
    @classmethod
    def validate_response(cls, value: str) -> str:
        return normalize_required_text(value, "응답")

    @model_validator(mode="after")
    def validate_attendance_response(self):
        if self.type != "attendance":
            return self

        try:
            payload = json.loads(self.response)
        except json.JSONDecodeError as exc:
            raise ValueError("출석 응답 형식이 올바르지 않습니다.") from exc

        if not isinstance(payload, dict):
            raise ValueError("출석 응답 형식이 올바르지 않습니다.")

        required_keys = ("checked", "already_checked")
        for key in required_keys:
            value = payload.get(key)
            if not isinstance(value, str) or not value.strip():
                raise ValueError("출석 응답과 중복출석 응답을 모두 입력해주세요.")

        optional_keys = {"not_streaming"}
        if any(key not in {*required_keys, *optional_keys} for key in payload):
            raise ValueError("지원하지 않는 출석 응답 항목입니다.")

        for value in payload.values():
            if not isinstance(value, str):
                raise ValueError("출석 응답 형식이 올바르지 않습니다.")
            if value.strip() and len(value.strip()) > MAX_CHAT_RESPONSE_CHARS:
                raise ValueError(f"출석 응답은 각 항목이 {MAX_CHAT_RESPONSE_CHARS}자 이하여야 합니다.")

        return self


class GreetingSaveRequest(BaseModel):
    keyword: str = Field(min_length=1, max_length=100)
    response: str = Field(min_length=1)

    @field_validator("keyword")
    @classmethod
    def validate_keyword(cls, value: str) -> str:
        return normalize_trigger(value, "키워드")

    @field_validator("response")
    @classmethod
    def validate_response(cls, value: str) -> str:
        return normalize_required_text(value, "응답")


class DeleteRequest(BaseModel):
    key: str = Field(min_length=1, max_length=100)

    @field_validator("key")
    @classmethod
    def validate_key(cls, value: str) -> str:
        return normalize_required_text(value, "삭제 대상")
