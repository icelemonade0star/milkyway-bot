from fastapi import APIRouter, Cookie, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.config import DASHBOARD_COOKIE_SECURE, MAX_CHAT_RESPONSE_CHARS, TEMPLATE_DIR
from app.core.database import get_async_db
from app.features.auth.platforms.chzzk import get_chzzk_auth
from app.features.auth.service import AuthService
from app.features.chat_overlay.schemas import OverlayPresetSaveRequest, OverlaySaveRequest
from app.features.chat_overlay.service import ChatOverlayService, DEFAULT_STYLE_OPTIONS, PresetDeleteResult
from app.features.dashboard.messages import save_error_detail
from app.features.dashboard.schemas import CommandSaveRequest, DeleteRequest, GreetingSaveRequest
from app.features.dashboard.service import DashboardService
from app.platforms.constants import PLATFORM_CHZZK

dashboard_router = APIRouter(prefix="/auth/dashboard", tags=["dashboard"])
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
DASHBOARD_PLATFORM = PLATFORM_CHZZK


def get_dashboard_session(dashboard_session: str = Cookie(None)):
    return security.verify_dashboard_session_token(dashboard_session)


@dashboard_router.get("/login")
async def dashboard_login(platform_auth=Depends(get_chzzk_auth)):
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

    dashboard_data = await DashboardService(db).get_dashboard_data(DASHBOARD_PLATFORM, session["channel_id"])
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


@dashboard_router.get("/overlay", response_class=HTMLResponse)
async def dashboard_overlay(
    request: Request,
    session: dict = Depends(get_dashboard_session),
    db: AsyncSession = Depends(get_async_db),
):
    channel, setting, presets = await ChatOverlayService(db).get_dashboard_overlay_data(DASHBOARD_PLATFORM, session["channel_id"])
    if not channel or not setting:
        raise HTTPException(status_code=403, detail="채널 정보를 찾을 수 없습니다.")

    return templates.TemplateResponse(
        "dashboard_overlay.html",
        {
            "request": request,
            "session": session,
            "channel": channel,
            "setting": setting,
            "style_mode": setting.style_mode if setting.style_mode is not None else "options",
            "base_style_options": DEFAULT_STYLE_OPTIONS.model_dump(),
            "style_options": setting.style_options if setting.style_options is not None else DEFAULT_STYLE_OPTIONS.model_dump(),
            "presets": [
                {
                    "id": preset.id,
                    "name": preset.name,
                    "style_mode": preset.style_mode,
                    "style_options": preset.style_options,
                    "custom_css": preset.custom_css,
                }
                for preset in presets
            ],
            "overlay_url": ChatOverlayService.overlay_url(setting.public_token),
        },
    )


@dashboard_router.post("/overlay")
async def save_dashboard_overlay(
    payload: OverlaySaveRequest,
    session: dict = Depends(get_dashboard_session),
    db: AsyncSession = Depends(get_async_db),
):
    channel, setting = await ChatOverlayService(db).update_setting(
        DASHBOARD_PLATFORM,
        session["channel_id"],
        payload.custom_css,
        payload.is_active,
        payload.style_mode,
        payload.style_options,
    )
    if not channel or not setting:
        raise HTTPException(status_code=403, detail="채널 정보를 찾을 수 없습니다.")
    return {
        "status": "success",
        "overlay_url": ChatOverlayService.overlay_url(setting.public_token),
    }


@dashboard_router.post("/overlay/presets")
async def save_dashboard_overlay_preset(
    payload: OverlayPresetSaveRequest,
    session: dict = Depends(get_dashboard_session),
    db: AsyncSession = Depends(get_async_db),
):
    preset = await ChatOverlayService(db).save_preset(
        DASHBOARD_PLATFORM,
        session["channel_id"],
        payload.name,
        payload.style_options,
        payload.custom_css,
        payload.style_mode,
    )
    if not preset:
        raise HTTPException(status_code=403, detail="채널 정보를 찾을 수 없습니다.")
    return {
        "status": "success",
        "preset": {
            "id": preset.id,
            "name": preset.name,
            "style_mode": preset.style_mode,
            "style_options": preset.style_options,
            "custom_css": preset.custom_css,
        },
    }


@dashboard_router.post("/overlay/presets/{preset_id}/apply")
async def apply_dashboard_overlay_preset(
    preset_id: int,
    session: dict = Depends(get_dashboard_session),
    db: AsyncSession = Depends(get_async_db),
):
    channel, setting, preset = await ChatOverlayService(db).apply_preset(
        DASHBOARD_PLATFORM,
        session["channel_id"],
        preset_id,
    )
    if not channel or not setting:
        raise HTTPException(status_code=403, detail="채널 정보를 찾을 수 없습니다.")
    if not preset:
        raise HTTPException(status_code=404, detail="프리셋을 찾을 수 없습니다.")
    return {
        "status": "success",
        "overlay_url": ChatOverlayService.overlay_url(setting.public_token),
        "preset": {
            "id": preset.id,
            "name": preset.name,
            "style_mode": preset.style_mode,
            "style_options": preset.style_options,
            "custom_css": preset.custom_css,
        },
    }


@dashboard_router.delete("/overlay/presets/{preset_id}")
async def delete_dashboard_overlay_preset(
    preset_id: int,
    session: dict = Depends(get_dashboard_session),
    db: AsyncSession = Depends(get_async_db),
):
    result = await ChatOverlayService(db).delete_preset(DASHBOARD_PLATFORM, session["channel_id"], preset_id)
    if result == PresetDeleteResult.CHANNEL_NOT_FOUND:
        raise HTTPException(status_code=403, detail="채널 정보를 찾을 수 없습니다.")
    if result == PresetDeleteResult.PRESET_NOT_FOUND:
        raise HTTPException(status_code=404, detail="프리셋을 찾을 수 없습니다.")
    return {"status": "success"}


@dashboard_router.post("/overlay/token")
async def rotate_dashboard_overlay_token(
    session: dict = Depends(get_dashboard_session),
    db: AsyncSession = Depends(get_async_db),
):
    channel, setting = await ChatOverlayService(db).rotate_token(DASHBOARD_PLATFORM, session["channel_id"])
    if not channel or not setting:
        raise HTTPException(status_code=403, detail="채널 정보를 찾을 수 없습니다.")
    return {
        "status": "success",
        "overlay_url": ChatOverlayService.overlay_url(setting.public_token),
    }


@dashboard_router.post("/commands")
async def save_command(
    payload: CommandSaveRequest,
    session: dict = Depends(get_dashboard_session),
    db: AsyncSession = Depends(get_async_db),
):
    success, reason = await DashboardService(db).save_command(
        DASHBOARD_PLATFORM,
        session["channel_id"],
        payload.command,
        payload.response,
        payload.cooldown_seconds,
        payload.is_active,
        payload.type,
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
    success = await DashboardService(db).delete_command(DASHBOARD_PLATFORM, session["channel_id"], payload.key)
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
        DASHBOARD_PLATFORM,
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
    success = await DashboardService(db).delete_greeting(DASHBOARD_PLATFORM, session["channel_id"], payload.key)
    if not success:
        raise HTTPException(status_code=404, detail="인사말을 찾을 수 없습니다.")
    return {"status": "success"}
