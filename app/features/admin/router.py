from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_async_db
from app.core.security import verify_admin_token
from app.db import models
from app.redis.redis_service import redis_client, RedisConfigService
from app.features.chat.service import ChatService
from app.features.live_state_poller import LiveStatePoller
from app.features.admin import schemas

admin_router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(verify_admin_token)],
)

redis_service = RedisConfigService()


def _serialize_live_state(channel, live_state=None, stream_session=None):
    return {
        "channel_id": channel.id,
        "platform": channel.platform,
        "platform_channel_id": channel.platform_channel_id,
        "channel_name": channel.channel_name,
        "is_active": channel.is_active,
        "status": live_state.status if live_state else "UNKNOWN",
        "current_stream_session_id": live_state.current_stream_session_id if live_state else None,
        "last_checked_at": live_state.last_checked_at if live_state else None,
        "opened_at": stream_session.opened_at if stream_session else None,
        "closed_at": stream_session.closed_at if stream_session else None,
        "stream_title": stream_session.stream_title if stream_session else None,
        "category": stream_session.category if stream_session else None,
    }


async def _get_live_state_rows(db: AsyncSession, platform: str | None = None, platform_channel_id: str | None = None):
    stmt = (
        select(models.V2Channel, models.V2ChannelLiveState, models.V2StreamSession)
        .outerjoin(
            models.V2ChannelLiveState,
            models.V2ChannelLiveState.channel_id == models.V2Channel.id,
        )
        .outerjoin(
            models.V2StreamSession,
            models.V2StreamSession.id == models.V2ChannelLiveState.current_stream_session_id,
        )
        .order_by(models.V2Channel.platform.asc(), models.V2Channel.channel_name.asc())
    )
    if platform:
        stmt = stmt.where(models.V2Channel.platform == platform)
    if platform_channel_id:
        stmt = stmt.where(models.V2Channel.platform_channel_id == platform_channel_id)

    return (await db.execute(stmt)).all()


async def _get_live_state_item(db: AsyncSession, platform: str, platform_channel_id: str):
    rows = await _get_live_state_rows(db, platform, platform_channel_id)
    if not rows:
        return None
    channel, live_state, stream_session = rows[0]
    return _serialize_live_state(channel, live_state, stream_session)


@admin_router.get(
    "/live-state",
    summary="v2 라이브 상태 목록 조회",
    description="v2 채널의 현재 라이브 상태와 현재 스트림 세션 정보를 조회합니다.",
    response_model=schemas.LiveStateListResponse,
)
async def get_live_states(
    platform: str | None = None,
    db: AsyncSession = Depends(get_async_db),
):
    rows = await _get_live_state_rows(db, platform=platform)
    channels = [
        _serialize_live_state(channel, live_state, stream_session)
        for channel, live_state, stream_session in rows
    ]
    return {
        "total_channels": len(channels),
        "channels": channels,
    }


@admin_router.get(
    "/live-state/{platform}/{platform_channel_id}",
    summary="v2 라이브 상태 조회",
    description="특정 v2 채널의 현재 라이브 상태와 현재 스트림 세션 정보를 조회합니다.",
    response_model=schemas.LiveStateItem,
)
async def get_live_state(
    platform: str,
    platform_channel_id: str,
    db: AsyncSession = Depends(get_async_db),
):
    item = await _get_live_state_item(db, platform, platform_channel_id)
    if not item:
        raise HTTPException(status_code=404, detail="v2 채널을 찾을 수 없습니다.")
    return item


@admin_router.post(
    "/live-state/{platform}/{platform_channel_id}/refresh",
    summary="v2 라이브 상태 단건 수동 갱신",
    description="특정 v2 채널의 라이브 상태를 플랫폼 API로 즉시 조회해 갱신합니다.",
    response_model=schemas.LiveStateRefreshResponse,
)
async def refresh_live_state(
    platform: str,
    platform_channel_id: str,
    db: AsyncSession = Depends(get_async_db),
):
    from app.core.database import get_session_factory

    session_factory = get_session_factory()
    if not session_factory:
        raise HTTPException(status_code=500, detail="DB 세션 팩토리가 초기화되지 않았습니다.")

    existing = await _get_live_state_item(db, platform, platform_channel_id)
    if not existing:
        raise HTTPException(status_code=404, detail="v2 채널을 찾을 수 없습니다.")

    refreshed = await LiveStatePoller(session_factory).poll_channel_by_platform_id(platform, platform_channel_id)
    if not refreshed:
        raise HTTPException(status_code=502, detail="라이브 상태 갱신에 실패했습니다.")

    db.expire_all()
    item = await _get_live_state_item(db, platform, platform_channel_id)
    return {
        "status": "success",
        "refreshed_channels": 1,
        "message": "라이브 상태가 갱신되었습니다.",
        "channel": item,
    }


@admin_router.post(
    "/live-state/refresh",
    summary="v2 라이브 상태 전체 수동 갱신",
    description="모든 활성 v2 채널의 라이브 상태를 플랫폼 API로 즉시 조회해 갱신합니다.",
    response_model=schemas.LiveStateRefreshResponse,
)
async def refresh_all_live_states():
    from app.core.database import get_session_factory

    session_factory = get_session_factory()
    if not session_factory:
        raise HTTPException(status_code=500, detail="DB 세션 팩토리가 초기화되지 않았습니다.")

    refreshed_count = await LiveStatePoller(session_factory).poll_once()
    return {
        "status": "success",
        "refreshed_channels": refreshed_count,
        "message": f"{refreshed_count}개 v2 채널의 라이브 상태가 갱신되었습니다.",
        "channel": None,
    }


@admin_router.get(
    "/greeting/redis/{channel_id}",
    summary="채널 Redis 인사말 조회",
    description="특정 채널에 캐싱된 Redis 인사말 목록을 반환합니다.",
    response_model=schemas.ChannelGreetingCacheResponse,
)
async def get_channel_greeting_cache(channel_id: str):
    cache_key = f"greetings:{channel_id}"
    try:
        raw = await redis_client.hgetall(cache_key)
        ttl = await redis_client.ttl(cache_key)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Redis 조회 실패: {e}")

    if not raw:
        return {
            "channel_id": channel_id,
            "cached": False,
            "count": 0,
            "ttl_seconds": None,
            "greetings": [],
        }

    greetings = [
        {"keyword": k, "response": v}
        for k, v in raw.items()
        if k != "__empty__"
    ]

    return {
        "channel_id": channel_id,
        "cached": True,
        "count": len(greetings),
        "ttl_seconds": ttl,
        "greetings": greetings,
    }


@admin_router.get(
    "/greeting/redis",
    summary="전체 채널 Redis 인사말 조회",
    description="Redis에 캐싱된 모든 채널의 인사말 목록을 반환합니다.",
    response_model=schemas.AllGreetingCacheResponse,
)
async def get_all_greeting_cache():
    try:
        keys = await redis_client.keys("greetings:*")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Redis 키 조회 실패: {e}")

    channels = []
    for key in keys:
        channel_id = key.removeprefix("greetings:")
        try:
            raw = await redis_client.hgetall(key)
            ttl = await redis_client.ttl(key)
        except Exception:
            continue

        greetings = [
            {"keyword": k, "response": v}
            for k, v in raw.items()
            if k != "__empty__"
        ]
        channels.append({
            "channel_id": channel_id,
            "count": len(greetings),
            "ttl_seconds": ttl,
            "greetings": greetings,
        })

    return {
        "total_channels": len(channels),
        "channels": channels,
    }


@admin_router.post(
    "/greeting/refresh/{channel_id}",
    summary="채널 인사말 Redis 수동 갱신",
    description="DB에 등록된 특정 채널의 인사말을 Redis에 즉시 갱신합니다.",
    response_model=schemas.GreetingRefreshResponse,
)
async def refresh_channel_greeting_cache(
    channel_id: str,
    db: AsyncSession = Depends(get_async_db),
):
    chat_service = ChatService(db)
    greetings = await chat_service.get_channel_greetings(channel_id)

    await redis_service.refresh_greetings_cache(channel_id)

    return {
        "status": "success",
        "channel_id": channel_id,
        "count": len(greetings),
        "message": f"인사말 {len(greetings)}개가 Redis에 갱신되었습니다.",
    }


@admin_router.post(
    "/greeting/refresh",
    summary="전체 채널 인사말 Redis 수동 갱신",
    description="DB에 등록된 모든 채널의 인사말을 Redis에 즉시 갱신합니다.",
    response_model=schemas.AllGreetingRefreshResponse,
)
async def refresh_all_greeting_cache(
    db: AsyncSession = Depends(get_async_db),
):
    result = await db.execute(
        select(models.V2Channel.platform_channel_id).where(models.V2Channel.is_active == True)
    )
    channel_ids = result.scalars().all()

    total_greetings = 0
    failed_channels = []

    for channel_id in channel_ids:
        try:
            chat_service = ChatService(db)
            greetings = await chat_service.get_channel_greetings(channel_id)
            await redis_service.refresh_greetings_cache(channel_id)
            total_greetings += len(greetings)
        except Exception as e:
            failed_channels.append({"channel_id": channel_id, "error": str(e)})

    return {
        "status": "success" if not failed_channels else "partial",
        "refreshed_channels": len(channel_ids) - len(failed_channels),
        "total_greetings": total_greetings,
        "failed_channels": failed_channels,
        "message": f"{len(channel_ids) - len(failed_channels)}개 채널의 인사말이 Redis에 갱신되었습니다.",
    }
