from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_async_db
from app.db.models import AuthToken
from app.redis.redis_service import redis_client, RedisConfigService
from app.features.chat.service import ChatService

admin_router = APIRouter(prefix="/admin", tags=["admin"])

redis_service = RedisConfigService()


@admin_router.get(
    "/greeting/redis/{channel_id}",
    summary="채널 Redis 인사말 조회",
    description="특정 채널에 캐싱된 Redis 인사말 목록을 반환합니다.",
)
async def get_channel_greeting_cache(channel_id: str):
    cache_key = f"greetings:{channel_id}"
    try:
        raw = await redis_client.hgetall(cache_key)
        ttl = await redis_client.ttl(cache_key)
    except Exception as e:
        return {"status": "error", "message": f"Redis 조회 실패: {e}"}

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
)
async def get_all_greeting_cache():
    try:
        keys = await redis_client.keys("greetings:*")
    except Exception as e:
        return {"status": "error", "message": f"Redis 키 조회 실패: {e}"}

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
)
async def refresh_all_greeting_cache(
    db: AsyncSession = Depends(get_async_db),
):
    result = await db.execute(select(AuthToken.channel_id))
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
