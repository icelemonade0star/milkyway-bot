from fastapi import APIRouter, BackgroundTasks, Cookie, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.config import CHZZK_REDIRECT_URL, DASHBOARD_COOKIE_SECURE, TEMPLATE_DIR
from app.core.database import get_async_db
from app.features.auth.service import AuthService
from app.features.chat.session_manager import session_manager
from app.platforms.constants import PLATFORM_CHZZK
from app.platforms.registry import get_auth_provider

AUTH_PLATFORM = PLATFORM_CHZZK

chzzk_auth_router = APIRouter(tags=["auth:chzzk"])
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))


def get_chzzk_auth(db: AsyncSession = Depends(get_async_db)):
    auth_service = AuthService(db)
    provider = get_auth_provider(AUTH_PLATFORM, auth_service)
    provider.redirect_url = CHZZK_REDIRECT_URL
    return provider


@chzzk_auth_router.get("/")
@chzzk_auth_router.get("/chzzk")
async def auth_redirect(platform_auth=Depends(get_chzzk_auth)):
    url, state = platform_auth.get_auth_url()

    response = RedirectResponse(url=url)
    response.set_cookie(key="oauth_state", value=state, httponly=True, max_age=300)
    return response


@chzzk_auth_router.get("/callback", response_class=HTMLResponse)
@chzzk_auth_router.get("/chzzk/callback", response_class=HTMLResponse)
async def callback_auth(
    request: Request,
    background_tasks: BackgroundTasks,
    code: str = Query(...),
    state: str = Query(...),
    oauth_state: str = Cookie(None),
    db: AsyncSession = Depends(get_async_db),
):
    platform_auth = get_chzzk_auth(db)

    if not oauth_state or state != oauth_state:
        raise HTTPException(status_code=400, detail="Invalid state")

    if not await platform_auth.get_access_token(code, state):
        raise HTTPException(status_code=400, detail="토큰 발급 실패")

    if not await platform_auth.get_user_info():
        raise HTTPException(status_code=400, detail="유저 정보 조회 실패")

    channel_id = platform_auth.channel_id
    if not channel_id:
        raise HTTPException(status_code=400, detail="채널 정보를 확인할 수 없습니다.")

    auth_service = AuthService(db)
    state_payload = security.verify_oauth_state_token(state)
    if state_payload and state_payload.get("purpose") == security.OAUTH_STATE_PURPOSE_DASHBOARD:
        registered_channel = await auth_service.get_auth_token_by_id(AUTH_PLATFORM, channel_id)
        if not registered_channel:
            raise HTTPException(status_code=403, detail="등록된 채널만 대시보드에 접근할 수 있습니다.")

        session_token = security.create_dashboard_session_token(channel_id, platform_auth.channel_name)
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
    background_tasks.add_task(session_manager.get_or_create_session, channel_id)

    channel_name = getattr(inserted_data, "channel_name", platform_auth.channel_name)
    return templates.TemplateResponse(
        "auth_callback.html",
        {"request": request, "channel_name": channel_name},
    )
