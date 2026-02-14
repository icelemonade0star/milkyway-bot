from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_async_db
from app.api.auth.auth_service import AuthService
from app.api.chat.chzzk_sessions import ChzzkSessions

chat_router = APIRouter(prefix="/chat", tags=["chat"])

@chat_router.get("/send")
async def send_chat_message(
    channel_id: str,
    message: str,
    db: AsyncSession = Depends(get_async_db)
):
    auth_service = AuthService(db)
    # 1. 세션 인스턴스 생성 (auth_service를 주입)
    chzzk_session = ChzzkSessions(channel_id, auth_service)

    # 2. 채팅 전송 (인자 수정: message만 전달)
    result = await chzzk_session.send_chat(message)
    
    if not result:
        return {"error": "채팅 전송에 실패했습니다."}
        
    return {"status": "success", "message": "채팅 전송에 성공했습니다."}
    