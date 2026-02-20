from app.redis.redis_service import RedisConfigService

from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_session_factory
from app.api.chat.chat_service import ChatService

from app.api.chat.session_manager import session_manager

async def on_message(channel_id: str, message_text: str):
    # 1. DB 세션 수동 생성
    async with get_session_factory() as db:
        chat_service = ChatService(db)
        redis_service = RedisConfigService(chat_service)
        
        # 2. Prefix 조회
        prefix = await redis_service.get_command_prefix(channel_id)
        
        if message_text.startswith(prefix):
            session = await session_manager.get_session(channel_id)
            parts = message_text[len(prefix):].split()
            if not parts:
                return # 접두사만 있는 경우
            
            command = parts[0]
            args = parts[1:]

            # 3. 명령어 실행
            await on_command(db, session, channel_id, command, args)

async def on_command(db: AsyncSession, session, channel_id: str, command: str, args: list):
    chat_service = ChatService(db)
    
    # 글로벌 명령어 조회 (이것도 나중엔 Redis에 캐싱할 수 있음)
    result = await chat_service.get_global_commands(command)

    if result:
        if result.type == "text":
            # 텍스트 응답 전송
            await session.send_chat(result.response)
        elif result.type == "system":
            # 시스템 명령어 (예: !prefix 변경 등) 처리 로직
            pass