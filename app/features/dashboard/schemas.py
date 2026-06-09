from pydantic import BaseModel, Field, field_validator


def normalize_trigger(value: str, label: str) -> str:
    parts = [part.strip() for part in value.strip().split("|")]
    if not parts or any(not part for part in parts):
        raise ValueError(f"{label}을 입력해주세요.")
    if any(len(part) < 2 for part in parts):
        raise ValueError(f"{label}는 2글자 이상이어야 합니다.")
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
