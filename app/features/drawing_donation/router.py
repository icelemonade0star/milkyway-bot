from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import TEMPLATE_DIR, PUBLIC_SITE_URL
from app.core.database import get_async_db
from app.features.dashboard.router import get_dashboard_session
from app.features.drawing_donation.schemas import DrawingDonationOptions, DrawingSaveRequest
from app.features.drawing_donation.service import DrawingDonationService
from app.features.drawing_donation.limits import limit_save_requests, limit_save_bytes

drawing_router = APIRouter(tags=["drawing-donation"])
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))


@drawing_router.get("/auth/dashboard/drawing", response_class=HTMLResponse)
async def dashboard_drawing(request: Request, session=Depends(get_dashboard_session), db: AsyncSession = Depends(get_async_db)):
    channel, setting = await DrawingDonationService(db).setting(session["channel_id"], create=True)
    return templates.TemplateResponse(request=request, name="dashboard_drawing.html", context={
        "request": request, "channel": channel, "options": DrawingDonationOptions.model_validate(setting.options),
        "drawing_url": f"{PUBLIC_SITE_URL}/drawing/chzzk/{channel.platform_channel_id}",
        "overlay_url": f"{PUBLIC_SITE_URL}/drawing/overlay/{setting.overlay_token}",
        "preview_path": f"/drawing/overlay/{setting.overlay_token}?preview=1",
    })


@drawing_router.post("/auth/dashboard/drawing")
async def save_drawing_options(options: DrawingDonationOptions, session=Depends(get_dashboard_session), db: AsyncSession = Depends(get_async_db)):
    _, setting = await DrawingDonationService(db).setting(session["channel_id"], create=True)
    setting.options = options.model_dump()
    await db.commit()
    return {"status": "success", "options": options.model_dump()}


@drawing_router.get("/drawing/chzzk/{channel_id}", response_class=HTMLResponse)
async def drawing_page(channel_id: str, request: Request, db: AsyncSession = Depends(get_async_db)):
    channel, setting = await DrawingDonationService(db).setting(channel_id)
    options = DrawingDonationOptions.model_validate(setting.options) if setting else DrawingDonationOptions()
    return templates.TemplateResponse(request=request, name="drawing.html", context={"request": request, "channel": channel, "options": options})


@drawing_router.post("/drawing/chzzk/{channel_id}")
async def save_drawing(channel_id: str, request: Request, db: AsyncSession = Depends(get_async_db)):
    await limit_save_requests(request)
    # PNG와 좌표 기록을 읽기 전에 요청 크기를 제한한다.
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 5_000_000:
            raise HTTPException(413, "그림 데이터가 너무 큽니다.")
    await limit_save_bytes(len(body))
    try:
        payload = DrawingSaveRequest.model_validate_json(bytes(body))
    except ValueError:
        raise HTTPException(422, "그림 기록 또는 PNG 형식이 올바르지 않습니다.")
    drawing = await DrawingDonationService(db).save_drawing(channel_id, payload)
    return {"hashtag": drawing.hashtag, "expires_at": drawing.expires_at.isoformat()}


@drawing_router.get("/drawing/overlay/{token}", response_class=HTMLResponse)
async def drawing_overlay(token: str, request: Request, preview: bool = False, db: AsyncSession = Depends(get_async_db)):
    setting = await DrawingDonationService(db).overlay_setting(token)
    return templates.TemplateResponse(request=request, name="drawing_overlay.html", context={
        "request": request, "options": DrawingDonationOptions.model_validate(setting.options).model_dump(),
        "poll_path": f"/drawing/overlay/{token}/next", "preview": preview,
    }, headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


@drawing_router.post("/drawing/overlay/{token}/next")
async def next_drawing(token: str, current: str | None = None, db: AsyncSession = Depends(get_async_db)):
    return await DrawingDonationService(db).next_playback(token, current)
