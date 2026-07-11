from fastapi import APIRouter, Cookie, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.config import DASHBOARD_COOKIE_SECURE, MAX_CHAT_RESPONSE_CHARS, TEMPLATE_DIR
from app.core.database import get_async_db
from app.features.auth.platforms.chzzk import get_chzzk_auth
from app.features.auth.service import AuthService
from app.features.chat_overlay.schemas import (
    ChatOverlayPresetSaveRequest,
    ChatOverlaySaveRequest,
    TimerOverlaySaveRequest,
)
from app.features.chat_overlay.service import (
    OVERLAY_KIND_CONFIG,
    ChatOverlayService,
    PresetDeleteResult,
)

def _normalize_options(raw: dict | None, overlay_kind: str) -> dict:
    config = OVERLAY_KIND_CONFIG[overlay_kind]
    try:
        return config.style_options_cls.model_validate(raw or {}).model_dump()
    except Exception:
        return config.default_options.model_dump()


def _preset_payload(preset) -> dict:
    return {
        "id": preset.id,
        "name": preset.name,
        "overlay_kind": preset.overlay_kind,
        "style_mode": preset.style_mode,
        "style_options": _normalize_options(preset.style_options, preset.overlay_kind),
        "custom_css": preset.custom_css,
    }
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
    channel, settings_by_kind, presets = await ChatOverlayService(db).get_dashboard_overlay_data(
        DASHBOARD_PLATFORM, session["channel_id"]
    )
    if not channel:
        raise HTTPException(status_code=403, detail="채널 정보를 찾을 수 없습니다.")

    chat_setting = settings_by_kind["chat"]
    timer_setting = settings_by_kind["timer"]

    return templates.TemplateResponse(
        "dashboard_overlay.html",
        {
            "request": request,
            "session": session,
            "channel": channel,
            "chat_style_mode": chat_setting.style_mode if chat_setting.style_mode is not None else "options",
            "timer_style_mode": timer_setting.style_mode if timer_setting.style_mode is not None else "options",
            "chat_style_defaults": OVERLAY_KIND_CONFIG["chat"].default_options.model_dump(),
            "timer_style_defaults": OVERLAY_KIND_CONFIG["timer"].default_options.model_dump(),
            "chat_style_options": _normalize_options(chat_setting.style_options, "chat"),
            "timer_style_options": _normalize_options(timer_setting.style_options, "timer"),
            "chat_custom_css": chat_setting.custom_css,
            "timer_custom_css": timer_setting.custom_css,
            "chat_presets": [_preset_payload(preset) for preset in presets],
            "overlay_url": ChatOverlayService.overlay_url(DASHBOARD_PLATFORM, channel.platform_channel_id),
            "timer_overlay_url": ChatOverlayService.timer_overlay_url(DASHBOARD_PLATFORM, channel.platform_channel_id),
        },
    )


async def _save_overlay(overlay_kind: str, payload, session: dict, db: AsyncSession):
    channel, setting = await ChatOverlayService(db).update_setting(
        DASHBOARD_PLATFORM,
        session["channel_id"],
        overlay_kind,
        payload.custom_css,
        payload.is_active,
        payload.style_mode,
        payload.style_options,
    )
    if not channel or not setting:
        raise HTTPException(status_code=403, detail="채널 정보를 찾을 수 없습니다.")
    return {
        "status": "success",
        "overlay_url": ChatOverlayService.overlay_url(DASHBOARD_PLATFORM, channel.platform_channel_id),
        "timer_overlay_url": ChatOverlayService.timer_overlay_url(DASHBOARD_PLATFORM, channel.platform_channel_id),
        "style_mode": setting.style_mode,
        "style_options": _normalize_options(setting.style_options, overlay_kind),
        "custom_css": setting.custom_css,
    }


@dashboard_router.post("/overlay/chat")
async def save_dashboard_chat_overlay(
    payload: ChatOverlaySaveRequest,
    session: dict = Depends(get_dashboard_session),
    db: AsyncSession = Depends(get_async_db),
):
    return await _save_overlay("chat", payload, session, db)


@dashboard_router.post("/overlay/timer")
async def save_dashboard_timer_overlay(
    payload: TimerOverlaySaveRequest,
    session: dict = Depends(get_dashboard_session),
    db: AsyncSession = Depends(get_async_db),
):
    return await _save_overlay("timer", payload, session, db)


@dashboard_router.post("/overlay/chat/presets")
async def save_dashboard_chat_overlay_preset(
    payload: ChatOverlayPresetSaveRequest,
    session: dict = Depends(get_dashboard_session),
    db: AsyncSession = Depends(get_async_db),
):
    preset = await ChatOverlayService(db).save_preset(
        DASHBOARD_PLATFORM,
        session["channel_id"],
        "chat",
        payload.name,
        payload.style_options,
        payload.custom_css,
        payload.style_mode,
    )
    if not preset:
        raise HTTPException(status_code=403, detail="채널 정보를 찾을 수 없습니다.")
    return {
        "status": "success",
        "preset": _preset_payload(preset),
    }


@dashboard_router.post("/overlay/chat/presets/{preset_id}/apply")
async def apply_dashboard_chat_overlay_preset(
    preset_id: int,
    session: dict = Depends(get_dashboard_session),
    db: AsyncSession = Depends(get_async_db),
):
    channel, setting, preset = await ChatOverlayService(db).apply_preset(
        DASHBOARD_PLATFORM,
        session["channel_id"],
        "chat",
        preset_id,
    )
    if not channel or not setting:
        raise HTTPException(status_code=403, detail="채널 정보를 찾을 수 없습니다.")
    if not preset:
        raise HTTPException(status_code=404, detail="프리셋을 찾을 수 없습니다.")
    return {
        "status": "success",
        "overlay_url": ChatOverlayService.overlay_url(DASHBOARD_PLATFORM, channel.platform_channel_id),
        "preset": _preset_payload(preset),
    }


@dashboard_router.delete("/overlay/chat/presets/{preset_id}")
async def delete_dashboard_chat_overlay_preset(
    preset_id: int,
    session: dict = Depends(get_dashboard_session),
    db: AsyncSession = Depends(get_async_db),
):
    result = await ChatOverlayService(db).delete_preset(DASHBOARD_PLATFORM, session["channel_id"], "chat", preset_id)
    if result == PresetDeleteResult.CHANNEL_NOT_FOUND:
        raise HTTPException(status_code=403, detail="채널 정보를 찾을 수 없습니다.")
    if result == PresetDeleteResult.PRESET_NOT_FOUND:
        raise HTTPException(status_code=404, detail="프리셋을 찾을 수 없습니다.")
    return {"status": "success"}


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
