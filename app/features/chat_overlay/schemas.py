from pydantic import BaseModel, Field, field_validator


class OverlaySaveRequest(BaseModel):
    custom_css: str = Field(default="", max_length=12000)
    is_active: bool = True

    @field_validator("custom_css")
    @classmethod
    def validate_custom_css(cls, value: str) -> str:
        lowered = value.lower()
        if "</style" in lowered or "<script" in lowered:
            raise ValueError("CSS만 입력할 수 있습니다.")
        if "@import" in lowered or "javascript:" in lowered:
            raise ValueError("외부 CSS import나 스크립트 URL은 사용할 수 없습니다.")
        return value
