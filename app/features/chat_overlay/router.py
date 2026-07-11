import logging
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import TEMPLATE_DIR
from app.core.database import get_async_db
from app.features.chat_overlay.broadcaster import chat_overlay_broadcaster, timer_overlay_broadcaster
from app.features.chat_overlay.overlay_manager import overlay_manager
from app.features.chat_overlay.schemas import ChatOverlayStyleOptions, TimerOverlayStyleOptions
from app.features.chat_overlay.service import ChatOverlayService
from app.features.chat_overlay.timer import overlay_timer_manager
from app.platforms.constants import PLATFORM_CHZZK

overlay_router = APIRouter(prefix="/overlay", tags=["chat-overlay"])
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
logger = logging.getLogger("ChatOverlayRouter")


def safe_chat_overlay_options(raw_options: dict | None) -> ChatOverlayStyleOptions:
    try:
        return ChatOverlayStyleOptions.model_validate(raw_options or {})
    except ValidationError as exc:
        logger.warning("잘못된 채팅 오버레이 옵션, 기본값 사용: %s", exc)
        return ChatOverlayStyleOptions()


def safe_timer_overlay_options(raw_options: dict | None) -> TimerOverlayStyleOptions:
    try:
        return TimerOverlayStyleOptions.model_validate(raw_options or {})
    except ValidationError as exc:
        logger.warning("잘못된 타이머 오버레이 옵션, 기본값 사용: %s", exc)
        return TimerOverlayStyleOptions()


def overlay_template_context(request: Request, channel, setting, options: ChatOverlayStyleOptions, websocket_path: str):
    return {
        "request": request,
        "channel": channel,
        "setting": setting,
        "overlay_message_ttl_ms": options.message_ttl_seconds * 1000,
        "overlay_name_color_mode": options.name_color_mode,
        "overlay_name_color_palette": ",".join(options.name_color_palette),
        "overlay_websocket_path": websocket_path,
    }


@overlay_router.get("/chat/chzzk/{platform_channel_id}", response_class=HTMLResponse)
async def chat_overlay_by_channel(
    platform_channel_id: str,
    request: Request,
    preset: str | None = Query(default=None),
    db: AsyncSession = Depends(get_async_db),
):
    service = ChatOverlayService(db)
    row = await service.get_setting_by_channel(PLATFORM_CHZZK, platform_channel_id, "chat")
    if not row:
        raise HTTPException(status_code=404, detail="Overlay not found.")

    channel, setting = row
    display_setting = setting

    if preset:
        preset_row = await service.get_preset_by_name(PLATFORM_CHZZK, platform_channel_id, preset, "chat")
        if preset_row:
            display_setting = preset_row

    options = safe_chat_overlay_options(display_setting.style_options)
    ws_path = f"/overlay/ws/chzzk/{platform_channel_id}"
    if preset:
        ws_path += f"?preset={quote(preset, safe='')}"
    return templates.TemplateResponse(
        "chat_overlay.html",
        overlay_template_context(request, channel, display_setting, options, ws_path),
    )


@overlay_router.get("/timer/chzzk/{platform_channel_id}", response_class=HTMLResponse)
async def timer_overlay_by_channel(
    platform_channel_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    service = ChatOverlayService(db)
    row = await service.get_setting_by_channel(PLATFORM_CHZZK, platform_channel_id, "timer")
    if not row:
        raise HTTPException(status_code=404, detail="Overlay not found.")

    channel, setting = row

    return templates.TemplateResponse(
        "timer_overlay.html",
        {
            "request": request,
            "channel": channel,
            "timer_css": setting.custom_css,
            "overlay_websocket_path": f"/overlay/ws/timer/chzzk/{platform_channel_id}",
        },
    )


@overlay_router.websocket("/ws/chzzk/{platform_channel_id}")
async def chat_overlay_ws_by_channel(
    websocket: WebSocket,
    platform_channel_id: str,
    preset: str | None = Query(default=None),
):
    session_factory = websocket.app.state.SessionLocal
    async with session_factory() as db:
        service = ChatOverlayService(db)
        row = await service.get_setting_by_channel(PLATFORM_CHZZK, platform_channel_id, "chat")
        if not row:
            await websocket.close(code=1008)
            return
        channel, setting = row
        display_setting = setting
        if preset:
            preset_row = await service.get_preset_by_name(PLATFORM_CHZZK, platform_channel_id, preset, "chat")
            if preset_row:
                display_setting = preset_row
        options = safe_chat_overlay_options(display_setting.style_options)
        platform_channel_id = channel.platform_channel_id

    await connect_overlay_websocket(websocket, platform_channel_id, options)


async def connect_overlay_websocket(websocket: WebSocket, platform_channel_id: str, options: ChatOverlayStyleOptions):
    await overlay_manager.ensure_raw_client(platform_channel_id)
    await chat_overlay_broadcaster.connect(
        platform_channel_id,
        websocket,
        blocked_nicknames=options.blocked_nicknames,
        blocked_roles=options.blocked_roles,
    )
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        chat_overlay_broadcaster.disconnect(platform_channel_id, websocket)


@overlay_router.websocket("/ws/timer/chzzk/{platform_channel_id}")
async def timer_overlay_ws_by_channel(websocket: WebSocket, platform_channel_id: str):
    session_factory = websocket.app.state.SessionLocal
    async with session_factory() as db:
        service = ChatOverlayService(db)
        row = await service.get_setting_by_channel(PLATFORM_CHZZK, platform_channel_id, "timer")
        if not row:
            await websocket.close(code=1008)
            return
        channel, _setting = row
        platform_channel_id = channel.platform_channel_id

    await connect_timer_overlay_websocket(websocket, platform_channel_id)


async def connect_timer_overlay_websocket(websocket: WebSocket, platform_channel_id: str):
    await timer_overlay_broadcaster.connect(platform_channel_id, websocket)
    await overlay_timer_manager.publish_snapshot(platform_channel_id)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        timer_overlay_broadcaster.disconnect(platform_channel_id, websocket)
