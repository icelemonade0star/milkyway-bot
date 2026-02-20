from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.chat.chzzk_sessions import ChzzkSessions
from app.api.chat.session_manager import session_manager

chat_router = APIRouter(prefix="/chat", tags=["chat"])


@chat_router.get("/send")
async def send_chat_message(
    channel_id: str,
    message: str
):
    chzzk_session = await session_manager.get_session(channel_id)

    # 2. 채팅 전송 (인자 수정: message만 전달)
    result = await chzzk_session.send_chat(message)
    
    if not result:
        return {"error": "채팅 전송에 실패했습니다."}
        
    return {"status": "success", "message": "채팅 전송에 성공했습니다."}


@chat_router.get("/create/session")
async def create_session(
    channel_id: str
):
    try:
        # 매니저에게 세션을 요청 (없으면 알아서 만들어서 줌)
        session, created = await session_manager.get_or_create_session(channel_id)
        
        if not created:
            return {
                "status": "already_exists", 
                "message": "이미 활성화된 세션입니다.",
                "channel_id": channel_id
            }

        return {
            "status": "success", 
            "message": "세션 생성 및 채팅 구독이 시작되었습니다.",
            "channel_id": channel_id
        }

    except Exception as e:
        return {
            "status": "error", 
            "message": f"세션 생성 중 오류 발생: {str(e)}"
        }

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
    
    await session_manager.remove_session(channel_id)
    
    return {"status": "success", "message": f"{channel_id} 세션이 종료되었습니다."}