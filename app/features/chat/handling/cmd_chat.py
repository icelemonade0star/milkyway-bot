import logging

from app.core.config import (
    ALLOWED_PREFIXES,
    MAX_CHAT_RESPONSE_CHARS,
    MAX_COMMAND_NAME_CHARS,
    MAX_COMMANDS_PER_CHANNEL,
)
from app.features.chat.handling.helpers import (
    CHAT_PLATFORM,
    get_josa,
    has_platform_emoticon,
    parse_command_and_content,
)
from app.features.chat.handling.placeholders import render_placeholders

logger = logging.getLogger("MessageHandling")


async def handle_list_commands(session, chat_service):
    all_cmds = await chat_service.get_all_global_commands()
    if all_cmds:
        cmd_names = [cmd.command.split('|')[0].strip() for cmd in all_cmds]
        await session.send_chat(f"기본 명령어: {', '.join(cmd_names)}")


async def handle_list_channel_commands(session, chat_service, channel_id):
    channel_cmds = await chat_service.get_channel_commands(channel_id, CHAT_PLATFORM)
    if channel_cmds:
        cmd_names = [cmd.command.split('|')[0].strip() for cmd in channel_cmds]
        await session.send_chat(f"채널 명령어: {', '.join(cmd_names)}")
    else:
        await session.send_chat("등록된 채널 명령어가 없습니다.")


async def handle_register_command(session, chat_service, channel_id, args):
    if len(args) < 2:
        await session.send_chat("사용법: !명령어등록 [명령어] [내용]")
        return

    new_cmd, new_response = parse_command_and_content(args)
    if not new_cmd or not new_response:
        await session.send_chat("명령어와 내용을 모두 입력해주세요.")
        return

    if has_platform_emoticon(new_cmd) or has_platform_emoticon(new_response):
        await session.send_chat("명령어 또는 내용에 이모티콘을 포함할 수 없습니다.")
        return

    status, actual_cmd = await chat_service.add_chat_command(
        channel_id,
        new_cmd,
        new_response,
        platform=CHAT_PLATFORM,
    )

    if status in ("created", "updated"):
        josa = get_josa(actual_cmd, "이/가")
        verb = "수정" if status == "updated" else "등록"
        await session.send_chat(f"명령어 '{actual_cmd}'{josa} {verb}되었습니다.")
    elif status == "response_too_long":
        await session.send_chat(f"응답은 구분자(|)로 나눈 각 항목이 {MAX_CHAT_RESPONSE_CHARS}자 이하여야 합니다.")
    elif status == "command_too_long":
        await session.send_chat(f"명령어는 {MAX_COMMAND_NAME_CHARS}자 이하여야 합니다.")
    elif status == "limit_exceeded":
        await session.send_chat(f"명령어는 최대 {MAX_COMMANDS_PER_CHANNEL}개까지 등록할 수 있습니다.")
    else:
        josa = get_josa(new_cmd, "은/는")
        await session.send_chat(f"'{new_cmd}'{josa} 이미 존재하는 기본 명령어이거나 등록할 수 없는 명령어입니다.")


async def handle_delete_command(session, chat_service, channel_id, args):
    if len(args) < 1:
        await session.send_chat("사용법: 명령어삭제 [명령어]")
        return

    target_cmd, _ = parse_command_and_content(args)
    if not target_cmd:
        await session.send_chat("삭제할 명령어를 입력해주세요.")
        return

    cmd_obj = await chat_service.get_chat_command(channel_id, target_cmd, CHAT_PLATFORM)
    if not cmd_obj:
        await session.send_chat(f"존재하지 않는 명령어입니다: {target_cmd}")
        return

    actual_cmd = cmd_obj.command
    if await chat_service.delete_chat_command(channel_id, actual_cmd, CHAT_PLATFORM):
        josa = get_josa(actual_cmd, "이/가")
        await session.send_chat(f"명령어 '{actual_cmd}'{josa} 삭제되었습니다.")
    else:
        await session.send_chat("명령어 삭제에 실패했습니다.")


async def handle_update_prefix(session, channel_id, args, redis_service):
    if len(args) < 1:
        await session.send_chat("사용법: 접두사수정 [새접두사]")
        return

    new_prefix = args[0]
    if len(new_prefix) != 1 or new_prefix not in ALLOWED_PREFIXES:
        await session.send_chat(f"허용되지 않는 접두사입니다. 사용 가능: {', '.join(ALLOWED_PREFIXES)}")
        return

    await redis_service.update_command_prefix(channel_id, new_prefix, CHAT_PLATFORM)
    josa = get_josa(new_prefix, "으로/로")
    await session.send_chat(f"접두사가 '{new_prefix}'{josa} 변경되었습니다.")


async def handle_notice(session, args):
    if not args:
        await session.send_chat("사용법: !공지 [내용]")
        return

    message = " ".join(args)
    success = await session.send_notice(message)
    if not success:
        await session.send_chat("공지 등록에 실패했습니다.")


async def handle_text_response(session, cmd, user_name):
    await session.send_chat(render_placeholders(cmd.response, user_name))
