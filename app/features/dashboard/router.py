from fastapi import APIRouter, Cookie, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.config import DASHBOARD_COOKIE_SECURE, DEFAULT_PLATFORM, MAX_CHAT_RESPONSE_CHARS, TEMPLATE_DIR
from app.core.database import get_async_db
from app.features.auth.service import AuthService
from app.features.dashboard.messages import save_error_detail
from app.features.dashboard.schemas import CommandSaveRequest, DeleteRequest, GreetingSaveRequest
from app.features.dashboard.service import DashboardService
from app.platforms.registry import get_auth_provider

dashboard_router = APIRouter(prefix="/auth/dashboard", tags=["dashboard"])
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))


def get_platform_auth(db: AsyncSession = Depends(get_async_db)):
    auth_service = AuthService(db)
    return get_auth_provider(DEFAULT_PLATFORM, auth_service)


def get_dashboard_session(dashboard_session: str = Cookie(None)):
    return security.verify_dashboard_session_token(dashboard_session)


@dashboard_router.get("/login")
async def dashboard_login(platform_auth = Depends(get_platform_auth)):
    state = security.create_oauth_state_token(security.OAUTH_STATE_PURPOSE_DASHBOARD)
    url, state = platform_auth.get_auth_url(state=state)

    response = RedirectResponse(url=url)
    response.set_cookie(
        key="oauth_state",
        value=state,
        httponly=True,
        secure=DASHBOARD_COOKIE_SECURE,
        max_age=300,
        samesite="lax",
    )
    return response


@dashboard_router.get("/logout")
async def dashboard_logout():
    response = RedirectResponse(url="/auth/dashboard", status_code=303)
    response.delete_cookie(security.DASHBOARD_SESSION_COOKIE)
    return response


@dashboard_router.get("", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    dashboard_session: str = Cookie(None),
    db: AsyncSession = Depends(get_async_db),
):
    try:
        session = security.verify_dashboard_session_token(dashboard_session)
    except HTTPException:
        return templates.TemplateResponse("dashboard_login.html", {"request": request})

    dashboard_data = await DashboardService(db).get_dashboard_data(session["channel_id"])
    if not dashboard_data:
        raise HTTPException(status_code=403, detail="등록된 채널 정보를 찾을 수 없습니다.")

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "session": session,
            "dashboard": dashboard_data,
            "limits": {
                "max_chat_response_chars": MAX_CHAT_RESPONSE_CHARS,
            },
        },
    )


@dashboard_router.post("/commands")
async def save_command(
    payload: CommandSaveRequest,
    session: dict = Depends(get_dashboard_session),
    db: AsyncSession = Depends(get_async_db),
):
    success, reason = await DashboardService(db).save_command(
        session["channel_id"],
        payload.command,
        payload.response,
        payload.cooldown_seconds,
        payload.is_active,
    )
    if not success:
        raise HTTPException(status_code=400, detail=save_error_detail("commands", reason))
    return {"status": "success"}


@dashboard_router.delete("/commands")
async def delete_command(
    payload: DeleteRequest,
    session: dict = Depends(get_dashboard_session),
    db: AsyncSession = Depends(get_async_db),
):
    success = await DashboardService(db).delete_command(session["channel_id"], payload.key)
    if not success:
        raise HTTPException(status_code=404, detail="명령어를 찾을 수 없습니다.")
    return {"status": "success"}


@dashboard_router.post("/greetings")
async def save_greeting(
    payload: GreetingSaveRequest,
    session: dict = Depends(get_dashboard_session),
    db: AsyncSession = Depends(get_async_db),
):
    success, reason = await DashboardService(db).save_greeting(
        session["channel_id"],
        payload.keyword,
        payload.response,
    )
    if not success:
        raise HTTPException(status_code=400, detail=save_error_detail("greetings", reason))
    return {"status": "success"}


@dashboard_router.delete("/greetings")
async def delete_greeting(
    payload: DeleteRequest,
    session: dict = Depends(get_dashboard_session),
    db: AsyncSession = Depends(get_async_db),
):
    success = await DashboardService(db).delete_greeting(session["channel_id"], payload.key)
    if not success:
        raise HTTPException(status_code=404, detail="인사말을 찾을 수 없습니다.")
    return {"status": "success"}
