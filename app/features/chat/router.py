from fastapi import APIRouter, Depends, HTTPException

from app.core.security import verify_admin_token
from app.features.chat.session_manager import session_manager
from app.features.chat.schemas import (
    ChatSendResponse,
    SessionCreateResponse,
    ActiveSessionsResponse,
    MessageResponse,
)

chat_router = APIRouter(prefix="/chat", tags=["chat"])


@chat_router.get("/send", response_model=ChatSendResponse, dependencies=[Depends(verify_admin_token)])
async def send_message(
    channel_id: str,
    message: str
):
    chzzk_session = session_manager.get_existing_session(channel_id)
    if not chzzk_session:
        raise HTTPException(status_code=404, detail="활성화된 세션이 없습니다.")

    result = await chzzk_session.send_chat(message)
    if not result:
        raise HTTPException(status_code=500, detail="채팅 전송에 실패했습니다.")

    return {"status": "success", "message": "채팅 전송에 성공했습니다."}


@chat_router.get("/create/session", response_model=SessionCreateResponse, dependencies=[Depends(verify_admin_token)])
async def create_session(
    channel_id: str
):
    _, created = await session_manager.get_or_create_session(channel_id)

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


@chat_router.get("/create/session/force", response_model=SessionCreateResponse, dependencies=[Depends(verify_admin_token)])
async def force_create_session(
    channel_id: str
):
    await session_manager.get_or_create_session(channel_id, force_recreate=True)

    return {
        "status": "success",
        "message": "세션이 강제로 재생성 및 채팅 구독이 시작되었습니다.",
        "channel_id": channel_id
    }


@chat_router.get("/active-sessions", response_model=ActiveSessionsResponse)
async def get_active_sessions():
    return {
        "count": len(session_manager.active_sessions),
        "channels": list(session_manager.active_sessions.keys())
    }


@chat_router.get("/close/session", response_model=MessageResponse, dependencies=[Depends(verify_admin_token)])
async def close_session(channel_id: str):
    session = session_manager.get_existing_session(channel_id)
    if not session:
        raise HTTPException(status_code=404, detail="활성화된 세션이 없습니다.")

    await session_manager.remove_session(channel_id)

    return {"status": "success", "message": f"{channel_id} 세션이 종료되었습니다."}
