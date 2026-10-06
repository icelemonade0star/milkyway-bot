import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Literal, overload

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.db.models import V2Channel, V2DrawingDonationSetting, V2DonationDrawing, V2DrawingDonationQueue
from app.features.drawing_donation.schemas import DrawingDonationOptions, DrawingSaveRequest
from app.platforms.constants import PLATFORM_CHZZK

TAG_PATTERN = re.compile(r"(?<![\w#])#mw-[a-f0-9]{24}(?!\w)", re.IGNORECASE)
RETENTION_HOURS = 1


def drawing_tags(text) -> list[str]:
    if not isinstance(text, str):
        return []
    return list(dict.fromkeys(tag.lower() for tag in TAG_PATTERN.findall(text)))[:5]


def utc(dt):
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


class DrawingDonationService:
    def __init__(self, db):
        self.db = db

    async def channel(self, platform_channel_id):
        return (await self.db.execute(select(V2Channel).where(
            V2Channel.platform == PLATFORM_CHZZK, V2Channel.platform_channel_id == platform_channel_id,
            V2Channel.is_active.is_(True),
        ))).scalar_one_or_none()

    @overload
    async def setting(self, platform_channel_id: str, create: Literal[True]) -> tuple[V2Channel, V2DrawingDonationSetting]: ...

    @overload
    async def setting(self, platform_channel_id: str, create: Literal[False] = False) -> tuple[V2Channel, V2DrawingDonationSetting | None]: ...

    @overload
    async def setting(self, platform_channel_id: str, create: bool) -> tuple[V2Channel, V2DrawingDonationSetting | None]: ...

    async def setting(self, platform_channel_id: str, create: bool = False) -> tuple[V2Channel, V2DrawingDonationSetting | None]:
        channel = await self.channel(platform_channel_id)
        if not channel:
            raise HTTPException(404, "채널을 찾을 수 없습니다.")
        setting = await self.db.get(V2DrawingDonationSetting, channel.id)
        if setting is None and create:
            setting = V2DrawingDonationSetting(
                channel_id=channel.id, overlay_token=secrets.token_urlsafe(32),
                options=DrawingDonationOptions().model_dump(),
            )
            self.db.add(setting)
            try:
                await self.db.commit()
            except IntegrityError:
                await self.db.rollback()
                setting = await self.db.get(V2DrawingDonationSetting, channel.id)
                if setting is None:
                    raise
        return channel, setting

    async def save_drawing(self, channel_id, payload: DrawingSaveRequest):
        channel, setting = await self.setting(channel_id)
        if setting is None or not DrawingDonationOptions.model_validate(setting.options).enabled:
            raise HTTPException(403, "현재 그림 도네이션을 받지 않는 채널입니다.")
        existing = (await self.db.execute(select(V2DonationDrawing).where(
            V2DonationDrawing.save_key == payload.save_key,
        ))).scalar_one_or_none()
        if existing:
            if existing.channel_id != channel.id:
                raise HTTPException(409, "저장 식별자가 이미 사용되었습니다.")
            if utc(existing.expires_at) <= datetime.now(timezone.utc):
                raise HTTPException(410, "그림 사용 시간이 지났습니다. 페이지를 새로고침해 다시 저장해주세요.")
            return existing
        drawing = V2DonationDrawing(
            channel_id=channel.id, save_key=payload.save_key, hashtag="#mw-" + secrets.token_hex(12),
            recording=payload.recording.model_dump(), final_png=payload.final_png,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=RETENTION_HOURS),
        )
        self.db.add(drawing)
        try:
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            existing = (await self.db.execute(select(V2DonationDrawing).where(
                V2DonationDrawing.save_key == payload.save_key, V2DonationDrawing.channel_id == channel.id,
            ))).scalar_one_or_none()
            if not existing:
                raise
            if utc(existing.expires_at) <= datetime.now(timezone.utc):
                raise HTTPException(410, "그림 사용 시간이 지났습니다. 페이지를 새로고침해 다시 저장해주세요.")
            return existing
        return drawing

    async def enqueue_donation(self, channel_id, payload):
        tags = drawing_tags(payload.get("donationText"))
        if not tags:
            return None
        channel, setting = await self.setting(channel_id)
        if setting is None:
            return None
        options = DrawingDonationOptions.model_validate(setting.options)
        amount = payload.get("payAmount")
        if not options.enabled or not isinstance(amount, (str, int)) or isinstance(amount, bool):
            return None
        if not re.fullmatch(r"[0-9]{1,12}", str(amount)) or int(amount) < options.minimum_amount:
            return None
        for tag in tags:
            drawing = (await self.db.execute(select(V2DonationDrawing).where(
                V2DonationDrawing.channel_id == channel.id, V2DonationDrawing.hashtag == tag,
                V2DonationDrawing.expires_at > datetime.now(timezone.utc),
            ).with_for_update())).scalar_one_or_none()
            if drawing is None:
                continue
            queue = V2DrawingDonationQueue(
                channel_id=channel.id, drawing_id=drawing.id,
                nickname=str(payload.get("donatorNickname") or "익명")[:255], amount=int(amount),
            )
            self.db.add(queue)
            await self.db.commit()
            return queue
        return None

    async def overlay_setting(self, token, lock=False):
        query = select(V2DrawingDonationSetting).join(V2Channel).where(
            V2DrawingDonationSetting.overlay_token == token, V2Channel.is_active.is_(True),
        )
        if lock:
            query = query.with_for_update(of=V2DrawingDonationSetting)
        setting = (await self.db.execute(query)).scalar_one_or_none()
        if setting is None:
            raise HTTPException(404, "오버레이를 찾을 수 없습니다.")
        return setting

    async def next_playback(self, token, current_id=None):
        # 설정 행 잠금으로 여러 OBS/미리보기 연결이 같은 대기열을 동시에 넘기지 않게 한다.
        setting = await self.overlay_setting(token, lock=True)
        options = DrawingDonationOptions.model_validate(setting.options)
        now = datetime.now(timezone.utc)
        result = None
        playing_id = None
        if options.enabled:
            jobs = (await self.db.execute(select(V2DrawingDonationQueue).join(V2DonationDrawing).where(
                V2DrawingDonationQueue.channel_id == setting.channel_id,
                V2DrawingDonationQueue.status.in_(["queued", "playing"]),
                V2DonationDrawing.expires_at > now,
            ).order_by(V2DrawingDonationQueue.created_at, V2DrawingDonationQueue.id).limit(2)
                .with_for_update(of=V2DonationDrawing))).scalars().all()
            for job in jobs:
                if job.status == "queued":
                    job.status, job.started_at = "playing", now
                    job.playback = options.model_dump()
                playback = DrawingDonationOptions.model_validate(job.playback)
                elapsed_ms = max(0, int((now - utc(job.started_at)).total_seconds() * 1000))
                if elapsed_ms >= (playback.replay_seconds + playback.hold_seconds) * 1000:
                    job.status = "done"
                    continue
                playing_id = str(job.id)
                if playing_id == current_id:
                    break
                drawing = await self.db.get(V2DonationDrawing, job.drawing_id)
                result = {
                    "id": str(job.id), "hashtag": drawing.hashtag, "nickname": job.nickname,
                    "amount": job.amount, "recording": drawing.recording, "final_png": drawing.final_png,
                    "elapsed_ms": elapsed_ms, "options": playback.model_dump(),
                }
                break
        await self.db.commit()
        return {"playback": result, "current_id": playing_id, "options": options.model_dump()}

    async def delete_expired_drawings(self, *, now=None, batch_size=250) -> int:
        cutoff = now if now is not None else datetime.now(timezone.utc)
        ids = (await self.db.execute(select(V2DonationDrawing.id).where(
            V2DonationDrawing.expires_at <= cutoff,
        ).order_by(V2DonationDrawing.expires_at, V2DonationDrawing.id).limit(batch_size)
            .with_for_update(skip_locked=True))).scalars().all()
        if ids:
            # FK의 ON DELETE CASCADE로 대기·재생·완료 항목도 같은 트랜잭션에서 삭제한다.
            await self.db.execute(delete(V2DonationDrawing).where(V2DonationDrawing.id.in_(ids)))
        await self.db.commit()
        return len(ids)
