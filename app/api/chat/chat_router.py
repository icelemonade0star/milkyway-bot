from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_async_db
from app.api.auth.auth_service import AuthService
from app.api.chat.chzzk_sessions import ChzzkSessions
from app.api.chat.session_manager import session_manager

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


@chat_router.get("/create/session")
async def create_session(
    channel_id: str,
    db: AsyncSession = Depends(get_async_db)
):
    # 이미 연결된 세션이 있는지 확인
    if session_manager.get_session(channel_id):
        return {"status": "already_exists", "message": "이미 활성화된 세션입니다."}

    auth_service = AuthService(db)
    chzzk_session = ChzzkSessions(channel_id, auth_service)
    
    # 세션 생성
    await chzzk_session.create_session()

    # 세션 매니저에 세션 저장
    session_manager.add_session(channel_id, chzzk_session)
    
    # 채팅 구독 시작
    await chzzk_session.subscribe_chat()

    return {"status": "success", "message": "세션 생성 및 채팅 구독이 시작되었습니다."}

@chat_router.get("/active-sessions")
async def get_active_sessions():
    return {
        "count": len(session_manager.active_sessions),
        "channels": list(session_manager.active_sessions.keys())
    }

@chat_router.get("/close/session")
async def close_session(channel_id: str):
    session = session_manager.get_session(channel_id)
    if not session:
        return {"status": "error", "message": "활성화된 세션이 없습니다."}
    
    await session.disconnect()
    # 매니저에서 제거
    del session_manager.active_sessions[channel_id]
    
    return {"status": "success", "message": f"{channel_id} 세션이 종료되었습니다."}