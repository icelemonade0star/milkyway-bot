from fastapi import APIRouter, HTTPException, Depends, Query, Cookie, BackgroundTasks, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import DASHBOARD_COOKIE_SECURE, DEFAULT_PLATFORM, TEMPLATE_DIR
from app.core.database import get_async_db
from app.core import security
from app.features.auth.service import AuthService
from app.features.auth.schemas import AuthListResponse, TokenRefreshResponse
from app.features.chat.session_manager import session_manager
from app.platforms.registry import get_auth_provider

auth_router = APIRouter(prefix="/auth", tags=["auth"])
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

def get_platform_auth(db: AsyncSession = Depends(get_async_db)):
    auth_service = AuthService(db)
    return get_auth_provider(DEFAULT_PLATFORM, auth_service)

@auth_router.get("/")
async def auth_redirect(platform_auth = Depends(get_platform_auth)):
    url, state = platform_auth.get_auth_url()

    response = RedirectResponse(url=url)
    # 쿠키에 state 저장 (유효기간 5분)
    response.set_cookie(key="oauth_state", value=state, httponly=True, max_age=300)

    return response


@auth_router.get("/callback", response_class=HTMLResponse)
async def callback_auth(
    request: Request,
    background_tasks: BackgroundTasks,
    code: str = Query(...),
    state: str = Query(...),
    oauth_state: str = Cookie(None),
    db: AsyncSession = Depends(get_async_db),
):
    platform_auth = get_platform_auth(db)
   
    # 쿠키에 저장된 state와 네이버가 보낸 state 비교
    if not oauth_state or state != oauth_state:
        raise HTTPException(status_code=400, detail="Invalid state")

    if not await platform_auth.get_access_token(code, state):
        raise HTTPException(status_code=400, detail="토큰 발급 실패")
    
    if not await platform_auth.get_user_info():
        raise HTTPException(status_code=400, detail="유저 정보 조회 실패")


    auth_service = AuthService(db)
    state_payload = security.verify_oauth_state_token(state)
    if state_payload and state_payload.get("purpose") == security.OAUTH_STATE_PURPOSE_DASHBOARD:
        registered_channel = await auth_service.get_auth_token_by_id(platform_auth.channel_id)
        if not registered_channel:
            raise HTTPException(status_code=403, detail="등록된 채널만 대시보드에 접근할 수 있습니다.")

        session_token = security.create_dashboard_session_token(platform_auth.channel_id, platform_auth.channel_name)
        response = RedirectResponse(url="/auth/dashboard", status_code=303)
        response.delete_cookie("oauth_state")
        response.set_cookie(
            key=security.DASHBOARD_SESSION_COOKIE,
            value=session_token,
            httponly=True,
            secure=DASHBOARD_COOKIE_SECURE,
            samesite="lax",
            max_age=security.DASHBOARD_SESSION_TTL_SECONDS,
        )
        return response

    inserted_data = await auth_service.save_default_platform_auth(platform_auth)
    
    # [추가] 인증 완료 후 백그라운드에서 세션 생성 및 채팅 연결 시작
    background_tasks.add_task(session_manager.get_or_create_session, platform_auth.channel_id)
    
    channel_name = getattr(inserted_data, 'channel_name', platform_auth.channel_name)

    return templates.TemplateResponse(
        "auth_callback.html",
        {"request": request, "channel_name": channel_name}
    )


@auth_router.get("/list", response_model=AuthListResponse, dependencies=[Depends(security.verify_admin_token)])
async def get_auth_token_list(
    channel_name: str = Query(None, description="검색할 채널 이름 (선택 사항)"),
    db: AsyncSession = Depends(get_async_db)
):
    auth_service = AuthService(db)
    rows = await auth_service.get_auth_list(channel_name)
    
    # 결과를 딕셔너리 리스트로 변환하여 반환
    return {
        "count": len(rows),
        "items": [
            {
                "channel_id": row.channel_id,
                "channel_name": row.channel_name,
                "expires_at": row.expires_at,
                "created_at": getattr(row, 'created_at', None)
            } for row in rows
        ]
    }

@auth_router.post(
    "/refresh/{channel_id}",
    response_model=TokenRefreshResponse,
    dependencies=[Depends(security.verify_admin_token)],
)
async def refresh_token(
    channel_id: str,
    platform_auth = Depends(get_platform_auth),
    db: AsyncSession = Depends(get_async_db)
):
    # 1. 토큰 갱신
    new_token, status_code = await platform_auth.refresh_access_token(channel_id)
    if not new_token:
        raise HTTPException(status_code=500, detail="토큰 갱신에 실패했습니다.")

    # 2. 스트림 세션 동기화 (방송 중일 시 기록)
    from app.features.chat.service import ChatService
    chat_service = ChatService(db)
    await chat_service.sync_stream_session(channel_id)

    # 3. 활성화된 세션이 있다면 메모리 상의 토큰도 업데이트
    await session_manager.update_session_token(channel_id, new_token)

    return {"status": "success", "message": "토큰이 갱신되었습니다."}

# 예외처리. 따로 분리할것
@auth_router.post("/authenticate")
async def authenticate():
    raise HTTPException(status_code=401, detail="Unauthorized")
