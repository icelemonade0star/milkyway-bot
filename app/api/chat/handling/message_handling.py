import logging
from app.redis.redis_service import RedisConfigService

from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_session_factory
from app.api.chat.chat_service import ChatService

# 로거 설정
logger = logging.getLogger("MessageHandling")

async def on_message(channel_id: str, message_text: str):
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
            await on_command(db, session, channel_id, command, args)

async def on_command(db: AsyncSession, session, channel_id: str, command: str, args: list):
    chat_service = ChatService(db)
    
    # 글로벌 명령어 조회
    result = await chat_service.get_global_commands(command)

    if result and result.is_active:
        if result.type == "text":
            # 텍스트 응답 전송
            await session.send_chat(result.response)
            
        elif result.type == "system":
            # 시스템 명령어 처리
            if result.command == "명령어":
                # 모든 활성 글로벌 명령어 조회
                all_cmds = await chat_service.get_all_global_commands()
                if all_cmds:
                    cmd_names = [cmd.command for cmd in all_cmds]
                    response_message = f"기본 명령어: {', '.join(cmd_names)}"
                    await session.send_chat(response_message)