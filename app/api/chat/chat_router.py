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
    auth_data = await auth_service.get_auth_token_by_id(channel_id)

    if not auth_data:
        return {"error": "채널 ID에 해당하는 인증 정보가 없습니다."}
    
    access_token = auth_data.access_token

    result = await ChzzkSessions.send_chat(access_token, message)
    
    if not result:
        return {"error": "채팅 전송에 실패했습니다."}
    return {"message": "채팅 전송에 성공했습니다."}
    