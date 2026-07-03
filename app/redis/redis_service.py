import asyncio
import redis.asyncio as redis
import app.core.config as config
import logging
import re
import json
from dataclasses import dataclass

from app.core.database import get_session_factory
from app.db import models
from app.features.chat.service import ChatService
from app.platforms.registry import get_live_provider
from sqlalchemy import select

logger = logging.getLogger("RedisConfigService")

redis_client = redis.Redis(
    host=config.REDIS_HOST,
    port=config.REDIS_PORT,
    decode_responses=True,
    max_connections=10,  # 1GB 서버 환경: 기본 50개에서 축소
)

@dataclass(frozen=True)
class RedisChannelKey:
    platform: str
    platform_channel_id: str
    channel_uuid: str


_CHANNEL_KEY_CACHE_MAX = 1000


class RedisConfigService:
    _channel_key_cache: dict[tuple[str, str], RedisChannelKey] = {}

    def __init__(self):
        pass

    @classmethod
    def _cache_channel_key(cls, key: tuple[str, str], value: RedisChannelKey):
        if len(cls._channel_key_cache) >= _CHANNEL_KEY_CACHE_MAX:
            # 삽입 순서 기준 오래된 절반 제거 (Python 3.7+ dict 순서 보장)
            evict = list(cls._channel_key_cache.keys())[: _CHANNEL_KEY_CACHE_MAX // 2]
            for k in evict:
                del cls._channel_key_cache[k]
        cls._channel_key_cache[key] = value

    @staticmethod
    def _channel_key(channel: RedisChannelKey) -> str:
        return f"{channel.platform}:{channel.platform_channel_id}:{channel.channel_uuid}"

    @classmethod
    def get_prefix_key(cls, channel: RedisChannelKey) -> str:
        return f"v2:config:prefix:{cls._channel_key(channel)}"

    @classmethod
    def get_greetings_key(cls, channel: RedisChannelKey) -> str:
        return f"v2:greetings:{cls._channel_key(channel)}"

    @classmethod
    def get_live_status_key(cls, channel: RedisChannelKey) -> str:
        return f"v2:live_status:{cls._channel_key(channel)}"

    @staticmethod
    def get_cooldown_key(platform: str, platform_channel_id: str, command: str) -> str:
        return f"v2:cooldown:{platform}:{platform_channel_id}:{command}"

    @classmethod
    def invalidate_channel_key(cls, platform: str, platform_channel_id: str):
        cls._channel_key_cache.pop((platform, platform_channel_id), None)

    @staticmethod
    def serialize_live_status(live_status) -> dict:
        return RedisConfigService.serialize_live_payload(
            status=live_status.status,
            platform=live_status.platform,
            platform_channel_id=live_status.platform_channel_id,
            opened_at=live_status.opened_at,
            closed_at=live_status.closed_at,
            title=live_status.title,
            category=live_status.category,
            thumbnail_url=live_status.thumbnail_url,
            raw=live_status.raw or {},
        )

    @staticmethod
    def serialize_live_payload(
        *,
        status: str,
        platform: str,
        platform_channel_id: str,
        opened_at=None,
        closed_at=None,
        title: str | None = None,
        category: str | None = None,
        thumbnail_url: str | None = None,
        raw: dict | None = None,
    ) -> dict:
        return {
            "status": status,
            "platform": platform,
            "platform_channel_id": platform_channel_id,
            "opened_at": opened_at.isoformat() if opened_at else None,
            "closed_at": closed_at.isoformat() if closed_at else None,
            "title": title,
            "category": category,
            "thumbnail_url": thumbnail_url,
            "raw": raw or {},
        }

    async def get_channel_key(
        self,
        platform_channel_id: str,
        platform: str,
        channel_uuid: str | None = None,
    ) -> RedisChannelKey | None:
        if channel_uuid:
            channel_key = RedisChannelKey(platform, platform_channel_id, str(channel_uuid))
            self._cache_channel_key((platform, platform_channel_id), channel_key)
            return channel_key

        cached = self._channel_key_cache.get((platform, platform_channel_id))
        if cached:
            return cached

        session_factory = get_session_factory()
        if not session_factory:
            return None

        async with session_factory() as db:
            channel = (await db.execute(
                select(models.V2Channel).where(
                    models.V2Channel.platform == platform,
                    models.V2Channel.platform_channel_id == platform_channel_id,
                )
            )).scalar_one_or_none()

        if not channel:
            return None
        channel_key = RedisChannelKey(platform, platform_channel_id, str(channel.id))
        self._cache_channel_key((platform, platform_channel_id), channel_key)
        return channel_key

    async def get_command_prefix(self, channel_id: str, platform: str) -> str:
        
        channel_key = await self.get_channel_key(channel_id, platform)
        cache_key = self.get_prefix_key(channel_key) if channel_key else None
        
        # 1. Redis에서 조회
        try:
            prefix = await redis_client.get(cache_key) if cache_key else None
            if prefix:
                return prefix
        except Exception as e:
            logger.warning("Redis 조회 실패, DB로 폴백: %s", e)
        
        # 2. Redis에 없으면 DB에서 조회
        session_factory = get_session_factory()
        if not session_factory:
            return "!"
            
        async with session_factory() as db:
            chat_service = ChatService(db)
            config_data = await chat_service.get_channel_config(channel_id, platform)

            if config_data and hasattr(config_data, 'command_prefix'):
                db_prefix = config_data.command_prefix

                # 3. 조회한 데이터를 Redis에 적재
                try:
                    if cache_key:
                        await redis_client.set(cache_key, db_prefix, ex=86400)
                except Exception as e:
                    logger.warning("Redis 접두사 저장 실패: %s", e)
                return db_prefix
        
        # 4. DB에도 정보가 없다면 기본값 반환
        return "!"

    async def update_command_prefix(self, channel_id: str, new_prefix: str, platform: str):
        # 1. DB 업데이트
        session_factory = get_session_factory()
        if not session_factory:
            return
            
        async with session_factory() as db:
            chat_service = ChatService(db)
            
            # 기존 설정을 조회하여 보존
            current_config = await chat_service.get_channel_config(channel_id, platform)
            language = current_config.language if current_config else "ko"
            is_active = current_config.is_active if current_config else True

            await chat_service.update_channel_config(
                channel_id=channel_id, 
                command_prefix=new_prefix, 
                language=language, 
                is_active=is_active,
                platform=platform,
            )
        
        # 2. Redis 캐시 갱신
        channel_key = await self.get_channel_key(channel_id, platform)
        cache_key = self.get_prefix_key(channel_key) if channel_key else None
        try:
            if cache_key:
                await redis_client.set(cache_key, new_prefix, ex=86400)
        except Exception as e:
            logger.warning("Redis 접두사 갱신 실패: %s", e)

    def _should_respond(self, message: str, keyword: str) -> bool:
        """
        메시지가 인사말 키워드에 반응해야 하는지 판단합니다.
        1. 단순 포함 여부 체크 (빠른 필터링)
        2. 왼쪽 경계 검사 (Lookbehind): 앞에 다른 글자가 붙어있는지 확인
        3. 오른쪽 경계 검사 (Lookahead): 뒤에 다른 글자가 붙어있는지 확인
           단, 키워드 자체가 반복되는 경우
        """
        # | 로 구분된 키워드 처리
        keywords = [k.strip() for k in keyword.split('|') if k.strip()]

        for k in keywords:
            # 1. 키워드가 아예 없으면 다음으로
            if k.lower() not in message.lower():
                continue

            # 2. 정규표현식
            # (?<!\w): 앞 경계 확인 (앞에 문자 없음)
            # (?:...)+: 키워드가 1번 이상 반복됨 (비캡처 그룹)
            # (?!\w): 뒤 경계 확인 (뒤에 문자 없음)
            pattern = rf"(?<!\w)(?:{re.escape(k)})+(?!\w)"
            # re.IGNORECASE를 추가하여 영어 인사말(Hi/hi)도 구분 없이 인식하도록 개선
            if re.search(pattern, message, re.IGNORECASE):
                return True
        
        return False

    async def _prefetch_live_status(self, channel_id: str, platform: str):
        """Cache live status through the platform live provider. No DB writes here."""
        channel_key = await self.get_channel_key(channel_id, platform)
        if not channel_key:
            return
        cache_key = self.get_live_status_key(channel_key)
        try:
            if await redis_client.exists(cache_key):
                return

            provider = get_live_provider(platform)
            live_status = await provider.get_live_status(channel_id)

            if not live_status or live_status.status != "OPEN":
                await redis_client.set(cache_key, "CLOSE", ex=60)
                return

            await redis_client.set(cache_key, json.dumps(self.serialize_live_status(live_status)), ex=300)
        except Exception as e:
            logger.warning("방송 상태 프리페치 실패: %s", e)

    async def get_greeting_response(
        self,
        channel_id: str,
        message: str,
        platform: str,
    ) -> tuple[str | None, bool]:
        """
        메시지에 인사말 키워드가 포함되어 있는지 확인하고 응답과 매칭 여부를 함께 반환합니다.
        반환값: (응답 메시지, 인사말 매칭 여부)
        """
        channel_key = await self.get_channel_key(channel_id, platform)
        if not channel_key:
            return None, False
        cache_key = self.get_greetings_key(channel_key)

        try:
            # 1. Redis에서 해당 채널의 모든 응답 키워드와 메시지 조회 (해시 전체 조회)
            greetings = await redis_client.hgetall(cache_key)

            # 2. 데이터가 없으면 DB 로드와 방송 상태 프리워밍을 병렬 실행
            if not greetings:
                await asyncio.gather(
                    self.refresh_greetings_cache(channel_id, platform),
                    self._prefetch_live_status(channel_id, platform),
                )
                greetings = await redis_client.hgetall(cache_key)

            # 3. 키워드 포함 여부 검사
            if greetings:
                for keyword, response in greetings.items():
                    if keyword == "__empty__":
                        continue
                    if self._should_respond(message, keyword):
                        # 쿨타임 체크 (10초)
                        if await self.check_and_set_cooldown(channel_id, f"greeting:{keyword}", 10, platform):
                            return None, True
                        return response, True

        except Exception as e:
            logger.warning("Redis 인사말 조회 실패: %s", e)

        return None, False

    async def refresh_greetings_cache(self, channel_id: str, platform: str):
        """DB에서 인사말을 불러와 Redis에 캐싱합니다."""
        channel_key = await self.get_channel_key(channel_id, platform)
        if not channel_key:
            return

        session_factory = get_session_factory()
        if not session_factory:
            return

        async with session_factory() as db:
            chat_service = ChatService(db)
            greetings = await chat_service.get_channel_greetings(channel_id, platform)
            
            cache_key = self.get_greetings_key(channel_key)
            try:
                if greetings:
                    mapping = {g.keyword: g.response for g in greetings}
                    # Pipeline을 사용하여 여러 명령어를 하나의 트랜잭션으로 묶어서 전송 (네트워크 통신 비용 감소)
                    async with redis_client.pipeline(transaction=True) as pipe:
                        pipe.delete(cache_key)
                        pipe.hset(cache_key, mapping=mapping)
                        pipe.expire(cache_key, 86400)
                        await pipe.execute()
                else:
                    # 인사말 없는 채널도 캐싱하여 매 메시지마다 DB 재조회 방지 (5분 후 재확인)
                    async with redis_client.pipeline(transaction=True) as pipe:
                        pipe.delete(cache_key)
                        pipe.hset(cache_key, "__empty__", "1")
                        pipe.expire(cache_key, 300)
                        await pipe.execute()
            except Exception as e:
                logger.warning("Redis 인사말 캐시 갱신 실패: %s", e)

    async def check_and_set_cooldown(self, channel_id: str, command: str, cooldown_seconds: int, platform: str) -> bool:
        """
        쿨타임 체크 및 설정.
        쿨타임 중이면 True 반환, 아니면 쿨타임 설정 후 False 반환.
        """
        if cooldown_seconds <= 0:
            return False
            
        cache_key = self.get_cooldown_key(platform, channel_id, command)
        
        try:
            # SET key value EX seconds NX
            # 키가 존재하지 않을 때만 값을 설정하고, 성공 시 True 반환 (원자적)
            # was_set: True -> 쿨타임이 아니어서 새로 설정함 -> 쿨타임 상태가 아님 (False 반환)
            # was_set: False -> 이미 키가 존재하여 설정 실패 -> 쿨타임 상태임 (True 반환)
            was_set = await redis_client.set(cache_key, "1", ex=cooldown_seconds, nx=True)
            return not was_set

        except Exception as e:
            logger.warning("Redis 쿨타임 확인 실패: %s", e)
            return False # 에러 시 쿨타임 없이 실행 허용
