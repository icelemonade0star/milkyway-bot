import hashlib
import ipaddress
import logging
from collections.abc import Awaitable, Sequence
from typing import cast

from fastapi import HTTPException, Request
from redis.exceptions import RedisError

from app.core import config
from app.redis.redis_service import redis_client

logger = logging.getLogger(__name__)

# 확인과 증가를 한 번에 실행해 동시 요청이나 여러 API 프로세스의 우회를 막는다.
LIMIT_SCRIPT = """
local retry = 0
for i, key in ipairs(KEYS) do
    local offset = (i - 1) * 3
    local cost = tonumber(ARGV[offset + 1])
    local limit = tonumber(ARGV[offset + 2])
    local seconds = tonumber(ARGV[offset + 3])
    local current = tonumber(redis.call('GET', key) or '0')
    if current + cost > limit then
        retry = math.max(retry, redis.call('TTL', key), seconds * (current == 0 and 1 or 0), 1)
    end
end
if retry > 0 then return retry end
for i, key in ipairs(KEYS) do
    local offset = (i - 1) * 3
    local current = redis.call('INCRBY', key, ARGV[offset + 1])
    if current == tonumber(ARGV[offset + 1]) then
        redis.call('EXPIRE', key, ARGV[offset + 3])
    end
end
return 0
"""


def client_address(request: Request) -> str:
    # 공개 API에서는 헤더를 신뢰하지 않는다. 내부 Nginx가 덮어쓰는 X-Real-IP만 선택적으로 사용한다.
    address = request.client.host if request.client else "unknown"
    if config.DRAWING_DONATION_TRUST_PROXY_HEADERS:
        forwarded = request.headers.get("x-real-ip", "")
        try:
            return str(ipaddress.ip_address(forwarded))
        except ValueError:
            pass
    return address


async def consume_limits(limits: Sequence[tuple[str, int, int, int]], message: str) -> None:
    keys = [key for key, _, _, _ in limits]
    arguments = [value for _, cost, limit, seconds in limits for value in (cost, limit, seconds)]
    try:
        # redis-py는 동기·비동기 공용 타입을 선언하지만 이 클라이언트는 비동기이며 Lua는 정수를 반환한다.
        result = cast(Awaitable[int], redis_client.eval(LIMIT_SCRIPT, len(keys), *keys, *arguments))
        retry = int(await result)
    except RedisError as exc:
        logger.error("그림 저장 제한 확인 실패: %s", exc)
        raise HTTPException(503, "지금은 그림을 저장할 수 없습니다. 잠시 후 다시 시도해주세요.",
                            headers={"Retry-After": "30"}) from exc
    if retry:
        raise HTTPException(429, message, headers={"Retry-After": str(retry)})


async def limit_save_requests(request: Request) -> None:
    identity = hashlib.sha256(client_address(request).encode()).hexdigest()
    await consume_limits([
        (f"drawing:save:ip:minute:{identity}", 1, config.DRAWING_DONATION_SAVE_PER_MINUTE, 60),
        (f"drawing:save:ip:hour:{identity}", 1, config.DRAWING_DONATION_SAVE_PER_HOUR, 3600),
    ], "그림 저장 요청이 너무 많습니다. 잠시 후 다시 시도해주세요.")


async def limit_save_bytes(size: int) -> None:
    # 만료 후 정리까지의 최대 90분에 맞춰 전체 저장 요청량도 제한한다.
    await consume_limits([
        ("drawing:save:bytes", size, config.DRAWING_DONATION_SAVE_BYTE_BUDGET, 5400),
    ], "그림 저장 공간이 잠시 혼잡합니다. 잠시 후 다시 시도해주세요.")
