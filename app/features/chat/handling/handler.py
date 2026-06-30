import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.redis.redis_service import RedisConfigService
from app.features.chat.service import ChatService
from app.features.chat.handling.helpers import CHAT_PLATFORM, ADMIN_SYSTEM_COMMANDS
from app.features.chat.handling.placeholders import has_attendance_placeholders, render_placeholders
from app.features.chat.handling.attendance import (
    fire_attendance_task,
    handle_custom_attendance,
    handle_global_attendance,
    process_greeting_attendance_with_lock,
)
from app.features.chat.handling.cmd_chat import (
    handle_delete_command,
    handle_list_channel_commands,
    handle_list_commands,
    handle_register_command,
    handle_text_response,
    handle_update_prefix,
)
from app.features.chat.handling.cmd_greeting import (
    handle_delete_greeting,
    handle_list_greetings,
    handle_register_greeting,
)
from app.features.chat.handling.cmd_notification import (
    handle_delete_notification,
    handle_set_notification,
)

logger = logging.getLogger("MessageHandling")

_redis_service = RedisConfigService()


async def on_message(channel_id: str, message_text: str, role: str, user_id: str, user_name: str):
    from app.features.chat.session_manager import session_manager

    prefix = await _redis_service.get_command_prefix(channel_id, CHAT_PLATFORM)

    if not message_text.startswith(prefix):
        from app.core.database import get_session_factory
        session_factory = get_session_factory()
        if session_factory:
            greeting_resp, is_greeting = await _redis_service.get_greeting_response(
                channel_id,
                message_text.strip(),
                CHAT_PLATFORM,
            )

            if is_greeting:
                attendance_attempted = False
                attendance_result = None

                if greeting_resp and has_attendance_placeholders(greeting_resp):
                    attendance_attempted = True
                    attendance_result = await process_greeting_attendance_with_lock(channel_id, user_id, user_name)
                    if attendance_result is None:
                        attendance_result = {"total": 0, "streak": 0}

                    session = session_manager.get_existing_session(channel_id)
                    if session:
                        await session.send_chat(render_placeholders(greeting_resp, user_name, attendance_result))
                elif greeting_resp:
                    session = session_manager.get_existing_session(channel_id)
                    if session:
                        await session.send_chat(render_placeholders(greeting_resp, user_name, attendance_result))

                if not attendance_attempted:
                    fire_attendance_task(channel_id, user_id, user_name)
        return

    content = message_text[len(prefix):].strip()
    if not content:
        return

    parts = content.split()
    command = parts[0]
    args = parts[1:]

    from app.core.database import get_session_factory
    session_factory = get_session_factory()
    if not session_factory:
        logger.error("DB 세션 팩토리가 초기화되지 않았습니다.")
        return

    async with session_factory() as db:
        session = session_manager.get_existing_session(channel_id)
        if session:
            await on_command(db, session, channel_id, command, args, role, _redis_service, prefix, user_id, user_name)


async def on_command(
    db: AsyncSession,
    session,
    channel_id: str,
    command: str,
    args: list,
    role: str,
    redis_service: RedisConfigService,
    prefix: str,
    user_id: str,
    user_name: str,
):
    chat_service = ChatService(db)

    # NOTE: SQLAlchemy AsyncSession은 단일 세션 객체에 대한 동시 작업을 허용하지 않으므로
    # asyncio.gather 병렬 조회가 IllegalStateChangeError를 유발합니다.
    custom_cmd = await chat_service.get_chat_command(channel_id, command, CHAT_PLATFORM)
    result = await chat_service.get_global_commands(command)

    is_admin_system_command = (
        result
        and result.is_active
        and result.type == "system"
        and result.command in ADMIN_SYSTEM_COMMANDS
    )

    if custom_cmd and custom_cmd.is_active and not is_admin_system_command:
        if custom_cmd.type == 'global':
            if await redis_service.check_and_set_cooldown(channel_id, command, custom_cmd.cooldown_seconds, CHAT_PLATFORM):
                return
            command = custom_cmd.response
            result = await chat_service.get_global_commands(command)

        elif custom_cmd.type == "attendance":
            await handle_custom_attendance(session, chat_service, channel_id, custom_cmd, user_id, user_name, redis_service, command)
            return

        else:
            if await redis_service.check_and_set_cooldown(channel_id, command, custom_cmd.cooldown_seconds, CHAT_PLATFORM):
                return
            await handle_text_response(session, custom_cmd, user_name)
            return

    if not (result and result.is_active):
        return

    if result.type == "system" and result.command in ADMIN_SYSTEM_COMMANDS and role == 'common_user':
        return

    if await redis_service.check_and_set_cooldown(channel_id, command, result.cooldown_seconds, CHAT_PLATFORM):
        return

    if result.type == "text":
        await handle_text_response(session, result, user_name)
        return

    if result.type == "attendance":
        await handle_global_attendance(session, chat_service, channel_id, result, user_id, user_name, redis_service, command)
        return

    if result.type == "system":
        await _dispatch_system_command(session, db, chat_service, channel_id, result.command, args, user_name, redis_service)


async def _dispatch_system_command(session, db, chat_service, channel_id, command_name, args, user_name, redis_service):
    if command_name == "명령어":
        await handle_list_commands(session, chat_service)

    elif command_name == "채널명령어":
        await handle_list_channel_commands(session, chat_service, channel_id)

    elif command_name == "명령어등록":
        await handle_register_command(session, chat_service, channel_id, args)

    elif command_name == "명령어삭제":
        await handle_delete_command(session, chat_service, channel_id, args)

    elif command_name == "접두사수정":
        await handle_update_prefix(session, channel_id, args, redis_service)

    elif command_name == "인사등록":
        await handle_register_greeting(session, chat_service, channel_id, args, redis_service)

    elif command_name == "인사삭제":
        await handle_delete_greeting(session, chat_service, channel_id, args, redis_service)

    elif command_name == "인사목록":
        await handle_list_greetings(session, chat_service, channel_id)

    elif command_name == "알림설정":
        await handle_set_notification(session, db, channel_id, args, user_name)

    elif command_name == "알림삭제":
        await handle_delete_notification(session, db, channel_id)
