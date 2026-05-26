from app.core.config import (
    MAX_CHAT_RESPONSE_CHARS,
    MAX_COMMAND_NAME_CHARS,
    MAX_COMMANDS_PER_CHANNEL,
    MAX_GREETINGS_PER_CHANNEL,
)


def save_error_detail(resource: str, reason: str | None) -> str:
    if reason == "empty" and resource == "commands":
        return "명령어와 응답을 모두 입력해주세요."
    if reason == "empty" and resource == "greetings":
        return "키워드와 응답을 모두 입력해주세요."
    if reason == "command_too_long":
        return f"명령어는 {MAX_COMMAND_NAME_CHARS}자 이하여야 합니다."
    if reason == "response_too_long":
        return f"응답은 구분자(|)로 나눈 각 항목이 {MAX_CHAT_RESPONSE_CHARS}자 이하여야 합니다."
    if reason == "limit_exceeded" and resource == "commands":
        return f"명령어는 최대 {MAX_COMMANDS_PER_CHANNEL}개까지 등록할 수 있습니다."
    if reason == "limit_exceeded" and resource == "greetings":
        return f"인사말은 최대 {MAX_GREETINGS_PER_CHANNEL}개까지 등록할 수 있습니다."
    if reason == "reserved":
        return "이미 존재하는 기본 명령어이거나 등록할 수 없는 명령어입니다."
    return "저장할 수 없습니다."
