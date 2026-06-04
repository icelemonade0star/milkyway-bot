from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.database import get_async_db
from app.features.auth import schemas
from app.features.auth.platforms.chzzk import chzzk_auth_router, get_chzzk_auth
from app.features.auth.service import AuthService
from app.features.chat.session_manager import session_manager
from app.platforms.constants import PLATFORM_CHZZK

AUTH_PLATFORM = PLATFORM_CHZZK

auth_router = APIRouter(prefix="/auth", tags=["auth"])
auth_router.include_router(chzzk_auth_router)


@auth_router.get(
    "/list",
    response_model=schemas.AuthListResponse,
    dependencies=[Depends(security.verify_admin_token)],
)
async def get_auth_token_list(
    channel_name: str = Query(None, description="검색할 채널 이름"),
    db: AsyncSession = Depends(get_async_db),
):
    auth_service = AuthService(db)
    rows = await auth_service.get_auth_list(AUTH_PLATFORM, channel_name)

    return {
        "count": len(rows),
        "items": [
            {
                "channel_id": row.channel_id,
                "channel_name": row.channel_name,
                "expires_at": row.expires_at,
                "created_at": getattr(row, "created_at", None),
            }
            for row in rows
        ],
    }


@auth_router.post(
    "/refresh/{channel_id}",
    response_model=schemas.TokenRefreshResponse,
    dependencies=[Depends(security.verify_admin_token)],
)
async def refresh_token(
    channel_id: str,
    platform_auth=Depends(get_chzzk_auth),
    db: AsyncSession = Depends(get_async_db),
):
    new_token, _status_code = await platform_auth.refresh_access_token(channel_id)
    if not new_token:
        raise HTTPException(status_code=500, detail="토큰 갱신에 실패했습니다.")

    from app.features.chat.service import ChatService

    chat_service = ChatService(db)
    await chat_service.sync_stream_session(channel_id, AUTH_PLATFORM)
    await session_manager.update_session_token(channel_id, new_token)

    return {"status": "success", "message": "토큰이 갱신되었습니다."}


@auth_router.post("/authenticate")
async def authenticate():
    raise HTTPException(status_code=401, detail="Unauthorized")
