import logging

from app.core.config import MAX_CHAT_RESPONSE_CHARS, MAX_GREETINGS_PER_CHANNEL
from app.features.chat.handling.helpers import (
    CHAT_PLATFORM,
    get_josa,
    has_platform_emoticon,
    parse_command_and_content,
)

logger = logging.getLogger("MessageHandling")


async def handle_register_greeting(session, chat_service, channel_id, args, redis_service):
    if len(args) < 2:
        await session.send_chat("사용법: !인사등록 [키워드] [응답]")
        return

    keywords_str, response = parse_command_and_content(args)
    if not keywords_str or not response:
        await session.send_chat("키워드와 응답을 모두 입력해주세요.")
        return

    if has_platform_emoticon(response):
        await session.send_chat("인사말 내용에 이모티콘을 포함할 수 없습니다.")
        return

    status, actual_keyword = await chat_service.add_greeting(
        channel_id,
        keywords_str,
        response,
        CHAT_PLATFORM,
    )

    if status == "limit_exceeded":
        await session.send_chat(f"인사말은 최대 {MAX_GREETINGS_PER_CHANNEL}개까지 등록할 수 있습니다.")
    elif status == "response_too_long":
        await session.send_chat(f"응답은 구분자(|)로 나눈 각 항목이 {MAX_CHAT_RESPONSE_CHARS}자 이하여야 합니다.")
    elif status == "updated":
        await redis_service.refresh_greetings_cache(channel_id, CHAT_PLATFORM)
        josa = get_josa(actual_keyword, "이/가")
        await session.send_chat(f"인사말 '{actual_keyword}'{josa} 수정되었습니다.")
    elif status == "created":
        await redis_service.refresh_greetings_cache(channel_id, CHAT_PLATFORM)
        josa = get_josa(actual_keyword, "이/가")
        await session.send_chat(f"인사말 '{actual_keyword}'{josa} 등록되었습니다.")
    else:
        await session.send_chat("인사말 등록에 실패했습니다.")


async def handle_delete_greeting(session, chat_service, channel_id, args, redis_service):
    if len(args) < 1:
        await session.send_chat("사용법: !인사삭제 [키워드]")
        return

    keywords_str, _ = parse_command_and_content(args)
    if not keywords_str:
        await session.send_chat("삭제할 키워드를 입력해주세요.")
        return

    target = await chat_service.get_greeting(channel_id, keywords_str, CHAT_PLATFORM)
    if not target:
        await session.send_chat("등록되지 않은 인사말입니다.")
        return

    actual_keyword = target.keyword
    if await chat_service.delete_greeting(channel_id, actual_keyword, CHAT_PLATFORM):
        await redis_service.refresh_greetings_cache(channel_id, CHAT_PLATFORM)
        josa = get_josa(actual_keyword, "이/가")
        await session.send_chat(f"인사말 '{actual_keyword}'{josa} 삭제되었습니다.")
    else:
        await session.send_chat("인사말 삭제에 실패했습니다.")


async def handle_list_greetings(session, chat_service, channel_id):
    greetings = await chat_service.get_channel_greetings(channel_id, CHAT_PLATFORM)
    if greetings:
        keywords = [g.keyword.split('|')[0].strip() for g in greetings]
        await session.send_chat(f"등록된 인사말: {', '.join(keywords)}")
    else:
        await session.send_chat("등록된 인사말이 없습니다.")
