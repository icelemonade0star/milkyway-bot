from fastapi import APIRouter, Cookie, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.config import DASHBOARD_COOKIE_SECURE, MAX_CHAT_RESPONSE_CHARS, MAX_COMMAND_NAME_CHARS, MAX_COMMANDS_PER_CHANNEL, MAX_GREETINGS_PER_CHANNEL, TEMPLATE_DIR
from app.core.database import get_async_db
from app.features.auth.chzzk_client import ChzzkAuth
from app.features.auth.service import AuthService
from app.features.dashboard.schemas import CommandSaveRequest, DeleteRequest, GreetingSaveRequest
from app.features.dashboard.service import DashboardService

dashboard_router = APIRouter(prefix="/auth/dashboard", tags=["dashboard"])
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))


def save_error_detail(resource: str, reason: str | None) -> str:
    if reason == "empty" and resource == "commands":
        return "명령어와 응답을 모두 입력해주세요."
    if reason == "empty" and resource == "greetings":
        return "키워드와 응답을 모두 입력해주세요."
    if reason == "command_too_long":
        return f"명령어는 {MAX_COMMAND_NAME_CHARS}자 이하여야 합니다."
    if reason == "response_too_long":
        return f"응답은 구분자(|)로 나눈 각 항목이 {MAX_CHAT_RESPONSE_CHARS}자 이하여야 합니다."
    if reason == "limit_exceeded" and resource == "commands":
        return f"명령어는 최대 {MAX_COMMANDS_PER_CHANNEL}개까지 등록할 수 있습니다."
    if reason == "limit_exceeded" and resource == "greetings":
        return f"인사말은 최대 {MAX_GREETINGS_PER_CHANNEL}개까지 등록할 수 있습니다."
    if reason == "reserved":
        return "이미 존재하는 기본 명령어이거나 등록할 수 없는 명령어입니다."
    return "저장할 수 없습니다."


def get_chzzk_auth(db: AsyncSession = Depends(get_async_db)) -> ChzzkAuth:
    auth_service = AuthService(db)
    return ChzzkAuth(auth_service)


def get_dashboard_session(dashboard_session: str = Cookie(None)):
    return security.verify_dashboard_session_token(dashboard_session)


@dashboard_router.get("/login")
async def dashboard_login(chzzk: ChzzkAuth = Depends(get_chzzk_auth)):
    state = security.create_oauth_state_token(security.OAUTH_STATE_PURPOSE_DASHBOARD)
    url, state = chzzk.get_auth_url(state=state)

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
