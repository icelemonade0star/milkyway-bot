import asyncio
import logging

from app.core.database import get_session_factory
from app.features.chat.service import ChatService
from app.features.chat.handling.helpers import (
    CHAT_PLATFORM,
    get_attendance_response_template,
    get_josa,
)
from app.features.chat.handling.placeholders import render_placeholders

logger = logging.getLogger("MessageHandling")

# 진행 중인 출석 처리를 추적 — 인사말 자동 출석과 출석 명령어가 같은 키를 공유해 중복 실행을 막습니다.
_attendance_in_flight: set[str] = set()


async def _process_attendance_in_new_session(channel_id: str, user_id: str, user_name: str):
    session_factory = get_session_factory()
    if not session_factory:
        return None
    async with session_factory() as db:
        chat_service = ChatService(db)
        return await chat_service.process_attendance(channel_id, user_id, user_name, CHAT_PLATFORM)


async def _attendance_task(channel_id: str, user_id: str, user_name: str):
    task_key = f"{channel_id}:{user_id}"
    try:
        await _process_attendance_in_new_session(channel_id, user_id, user_name)
    except Exception as e:
        logger.warning("출석 처리 실패 [%s/%s]: %s", channel_id, user_id, e)
    finally:
        _attendance_in_flight.discard(task_key)


async def process_greeting_attendance_with_lock(channel_id: str, user_id: str, user_name: str):
    """on_message 인사말 경로 전용: 자체 DB 세션을 열고 in-flight 락을 직접 관리합니다."""
    task_key = f"{channel_id}:{user_id}"
    if task_key in _attendance_in_flight:
        return None

    _attendance_in_flight.add(task_key)
    try:
        return await _process_attendance_in_new_session(channel_id, user_id, user_name)
    except Exception as e:
        logger.warning("출석 처리 실패 [%s/%s]: %s", channel_id, user_id, e)
        return None
    finally:
        _attendance_in_flight.discard(task_key)


def fire_attendance_task(channel_id: str, user_id: str, user_name: str) -> bool:
    """백그라운드 출석 태스크를 생성합니다. 이미 처리 중이면 False를 반환합니다."""
    task_key = f"{channel_id}:{user_id}"
    if task_key in _attendance_in_flight:
        return False
    _attendance_in_flight.add(task_key)
    asyncio.create_task(_attendance_task(channel_id, user_id, user_name))
    return True


async def handle_custom_attendance(session, chat_service, channel_id, custom_cmd, user_id, user_name, redis_service, command):
    """커스텀 attendance 타입 명령어를 처리합니다."""
    cooldown_key = f"{command}:user:{user_id}"
    if await redis_service.check_and_set_cooldown(channel_id, cooldown_key, custom_cmd.cooldown_seconds, CHAT_PLATFORM):
        return

    task_key = f"{channel_id}:{user_id}"
    if task_key in _attendance_in_flight:
        return

    _attendance_in_flight.add(task_key)
    try:
        result_att = await chat_service.process_attendance(channel_id, user_id, user_name, CHAT_PLATFORM)
        if result_att:
            template = get_attendance_response_template(custom_cmd.response, result_att["status"])
            if template:
                await session.send_chat(render_placeholders(template, user_name, result_att))
            elif result_att["status"] == "not_streaming":
                await session.send_chat(f"@{user_name}님 방송 중에만 출석할 수 있습니다.")
    finally:
        _attendance_in_flight.discard(task_key)


async def handle_global_attendance(session, chat_service, channel_id, result, user_id, user_name, redis_service, command):
    """글로벌 attendance 타입 명령어를 처리합니다."""
    cooldown_key = f"{command}:user:{user_id}"
    if await redis_service.check_and_set_cooldown(channel_id, cooldown_key, result.cooldown_seconds, CHAT_PLATFORM):
        return

    task_key = f"{channel_id}:{user_id}"
    if task_key in _attendance_in_flight:
        return

    _attendance_in_flight.add(task_key)
    try:
        result_att = await chat_service.process_attendance(channel_id, user_id, user_name, CHAT_PLATFORM)
        if result_att:
            if result_att["status"] == "checked":
                msg = f"@{user_name}님 출석 체크 완료! (연속 {result_att['streak']}일 / 총 {result_att['total']}일)"
                await session.send_chat(msg)
            elif result_att["status"] == "already_checked":
                msg = f"@{user_name}님은 이미 출석했습니다. (연속 {result_att['streak']}일 / 총 {result_att['total']}일)"
                await session.send_chat(msg)
            elif result_att["status"] == "not_streaming":
                msg = f"@{user_name}님 방송 중에만 출석할 수 있습니다."
                await session.send_chat(msg)
    finally:
        _attendance_in_flight.discard(task_key)
