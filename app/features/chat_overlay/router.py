from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import TEMPLATE_DIR
from app.core.database import get_async_db
from app.features.chat_overlay.broadcaster import chat_overlay_broadcaster
from app.features.chat_overlay.service import ChatOverlayService

overlay_router = APIRouter(prefix="/overlay", tags=["chat-overlay"])
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))


@overlay_router.get("/chat/{token}", response_class=HTMLResponse)
async def chat_overlay(token: str, request: Request, db: AsyncSession = Depends(get_async_db)):
    row = await ChatOverlayService(db).get_setting_by_token(token)
    if not row:
        raise HTTPException(status_code=404, detail="Overlay not found.")

    channel, setting = row
    return templates.TemplateResponse(
        "chat_overlay.html",
        {
            "request": request,
            "channel": channel,
            "setting": setting,
        },
    )


@overlay_router.websocket("/ws/{token}")
async def chat_overlay_ws(websocket: WebSocket, token: str):
    session_factory = websocket.app.state.SessionLocal
    async with session_factory() as db:
        row = await ChatOverlayService(db).get_setting_by_token(token)
        if not row:
            await websocket.close(code=1008)
            return
        channel, setting = row
        if not setting.is_active:
            await websocket.close(code=1008)
            return
        platform_channel_id = channel.platform_channel_id

    await chat_overlay_broadcaster.connect(platform_channel_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        chat_overlay_broadcaster.disconnect(platform_channel_id, websocket)
