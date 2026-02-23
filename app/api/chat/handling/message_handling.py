import logging
from app.redis.redis_service import RedisConfigService

from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_session_factory
from app.api.chat.chat_service import ChatService

# 로거 설정
logger = logging.getLogger("MessageHandling")

async def on_message(channel_id: str, message_text: str, role: str):
    # 순환 참조 방지를 위해 함수 내부에서 import
    from app.api.chat.session_manager import session_manager
   
    # 1. Redis 서비스 인스턴스 생성
    redis_service = RedisConfigService()
    
    # 2. Prefix 조회 (Redis -> DB Fallback)
    prefix = await redis_service.get_command_prefix(channel_id)
    
    # 접두사로 시작하지 않으면 무시
    if not message_text.startswith(prefix):
        return

    # 3. 명령어 파싱
    content = message_text[len(prefix):].strip()
    if not content:
        return # 접두사만 있는 경우

    parts = content.split()
    command = parts[0]
    args = parts[1:]

    # 4. DB 연결 및 명령어 실행
    session_factory = get_session_factory()
    if not session_factory:
        logger.error("DB Session Factory is not initialized.")
        return

    async with session_factory() as db:
        session = await session_manager.get_session(channel_id)
        if session:
            await on_command(db, session, channel_id, command, args, role)

async def on_command(db: AsyncSession, session, channel_id: str, command: str, args: list, role: str):
    chat_service = ChatService(db)
    
    # 글로벌 명령어 조회
    result = await chat_service.get_global_commands(command)

    if result and result.is_active:
        if result.type == "text":
            # 텍스트 응답 전송
            await session.send_chat(result.response)
            
        elif result.type == "system":
            # 시스템 명령어 처리
            # 관리자 권한이 필요한 명령어 목록
            admin_commands = ["명령어등록", "명령어수정", "명령어삭제", "접두사수정"]
            if result.command in admin_commands and role == 'common_user':
                return

            if result.command == "명령어":
                # 모든 활성 글로벌 명령어 조회
                all_cmds = await chat_service.get_all_global_commands()
                if all_cmds:
                    cmd_names = [cmd.command for cmd in all_cmds]
                    response_message = f"기본 명령어: {', '.join(cmd_names)}"
                    await session.send_chat(response_message)
            
            elif result.command == "개인서버명령어":
                # 채널 전용 커스텀 명령어 조회
                channel_cmds = await chat_service.get_channel_commands(channel_id)
                if channel_cmds:
                    cmd_names = [cmd.command for cmd in channel_cmds]
                    response_message = f"채널 명령어: {', '.join(cmd_names)}"
                    await session.send_chat(response_message)
                else:
                    await session.send_chat("등록된 채널 명령어가 없습니다.")
            
            elif result.command == "명령어등록":
                if len(args) < 2:
                    await session.send_chat("사용법: 명령어등록 [명령어] [내용]")
                    return
                new_cmd = args[0]
                new_response = " ".join(args[1:])
                success = await chat_service.add_chat_command(channel_id, new_cmd, new_response)
                if success:
                    await session.send_chat(f"명령어 '{new_cmd}'가 등록되었습니다.")
                else:
                    await session.send_chat(f"이미 존재하는 명령어입니다: {new_cmd}")

            elif result.command == "명령어수정":
                if len(args) < 2:
                    await session.send_chat("사용법: 명령어수정 [명령어] [내용]")
                    return
                target_cmd = args[0]
                new_response = " ".join(args[1:])
                success = await chat_service.update_chat_command(channel_id, target_cmd, new_response)
                if success:
                    await session.send_chat(f"명령어 '{target_cmd}'가 수정되었습니다.")
                else:
                    await session.send_chat(f"존재하지 않는 명령어입니다: {target_cmd}")

            elif result.command == "명령어삭제":
                if len(args) < 1:
                    await session.send_chat("사용법: 명령어삭제 [명령어]")
                    return
                target_cmd = args[0]
                success = await chat_service.delete_chat_command(channel_id, target_cmd)
                if success:
                    await session.send_chat(f"명령어 '{target_cmd}'가 삭제되었습니다.")
                else:
                    await session.send_chat(f"존재하지 않는 명령어입니다: {target_cmd}")

            elif result.command == "접두사수정":
                if len(args) < 1:
                    await session.send_chat("사용법: 접두사수정 [새접두사]")
                    return
                new_prefix = args[0]
                # RedisConfigService를 통해 DB와 Redis 모두 업데이트
                redis_service = RedisConfigService()
                await redis_service.update_command_prefix(channel_id, new_prefix)
                await session.send_chat(f"접두사가 '{new_prefix}'로 변경되었습니다.")

    else:
        # 글로벌 명령어가 아닐 경우, 채널 커스텀 명령어 확인 및 실행
        custom_cmd = await chat_service.get_chat_command(channel_id, command)
        if custom_cmd and custom_cmd.is_active:
             await session.send_chat(custom_cmd.response)
