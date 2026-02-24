import redis.asyncio as redis
from datetime import timedelta
import app.config as config

from app.db.database import get_session_factory
from app.api.chat.chat_service import ChatService

redis_client = redis.Redis(host=config.REDIS_HOST, port=config.REDIS_PORT, decode_responses=True)

class RedisConfigService:
    def __init__(self):
        # self.chat_service = chat_service
        pass

    @staticmethod
    def get_cache_key(channel_id: str):
        return f"config:prefix:{channel_id}"

    async def get_command_prefix(self, channel_id: str) -> str:
        
        cache_key = self.get_cache_key(channel_id)
        
        # 1. Redis에서 조회
        try:
            prefix = await redis_client.get(cache_key)
            if prefix:
                return prefix
        except Exception as e:
            print(f"⚠️ Redis 조회 실패 (DB 조회로 전환): {e}")
        
        # 2. Redis에 없으면 DB에서 조회
        session_factory = get_session_factory()
        if not session_factory:
            return "!"
            
        async with session_factory() as db:
            chat_service = ChatService(db)
            config_data = await chat_service.get_channel_config(channel_id)

            if config_data and hasattr(config_data, 'command_prefix'):
                db_prefix = config_data.command_prefix

                # 3. 조회한 데이터를 Redis에 적재
                try:
                    await redis_client.set(cache_key, db_prefix, ex=timedelta(days=1))
                except Exception as e:
                    print(f"⚠️ Redis 저장 실패: {e}")
                return db_prefix
        
        # 4. DB에도 정보가 없다면 기본값 반환
        return "!"

    async def update_command_prefix(self, channel_id: str, new_prefix: str, language: str = "ko", is_active: bool = True):
        # 1. DB 업데이트
        session_factory = get_session_factory()
        if not session_factory:
            return
            
        async with session_factory() as db:
            chat_service = ChatService(db)
            await chat_service.update_channel_config(
                channel_id=channel_id, 
                command_prefix=new_prefix, 
                language=language, 
                is_active=is_active
            )
        
        # 2. Redis 캐시 갱신
        cache_key = self.get_cache_key(channel_id)
        try:
            await redis_client.set(cache_key, new_prefix, ex=timedelta(days=1))
        except Exception as e:
            print(f"⚠️ Redis 갱신 실패: {e}")

    async def get_greeting_response(self, channel_id: str, message: str) -> str:
        """
        메시지가 인삿말 키워드와 일치하는지 확인하고 응답을 반환합니다.
        Redis Hash를 사용하여 O(1) 조회.
        """
        cache_key = f"greetings:{channel_id}"
        
        try:
            # 1. Redis에서 해당 키워드 조회
            response = await redis_client.hget(cache_key, message)
            if response:
                return response
                
            # 2. Redis에 키가 아예 없으면(만료/미로드) DB에서 로드 후 재시도
            if not await redis_client.exists(cache_key):
                await self.refresh_greetings_cache(channel_id)
                # 다시 조회
                return await redis_client.hget(cache_key, message)
                
        except Exception as e:
            print(f"⚠️ Redis 인삿말 조회 실패: {e}")
            
        return None

    async def refresh_greetings_cache(self, channel_id: str):
        """DB에서 인삿말을 불러와 Redis에 캐싱합니다."""
        session_factory = get_session_factory()
        if not session_factory:
            return

        async with session_factory() as db:
            chat_service = ChatService(db)
            greetings = await chat_service.get_channel_greetings(channel_id)
            
            cache_key = f"greetings:{channel_id}"
            try:
                # 기존 키 삭제 후 새로 등록 (삭제된 항목 반영 위해)
                await redis_client.delete(cache_key)
                if greetings:
                    mapping = {g.keyword: g.response for g in greetings}
                    await redis_client.hset(cache_key, mapping=mapping)
                    # 24시간 유지
                    await redis_client.expire(cache_key, timedelta(days=1))
            except Exception as e:
                print(f"⚠️ Redis 인삿말 캐싱 실패: {e}")

    async def add_greeting_cache(self, channel_id: str, keyword: str, response: str):
        """인삿말 하나를 Redis에 추가하거나 갱신합니다."""
        cache_key = f"greetings:{channel_id}"
        try:
            # 캐시가 존재하면 부분 업데이트 (TTL 유지)
            if await redis_client.exists(cache_key):
                await redis_client.hset(cache_key, keyword, response)
            else:
                # 캐시가 없으면 전체 로드 (TTL 설정 포함)
                await self.refresh_greetings_cache(channel_id)
        except Exception as e:
            print(f"⚠️ Redis 인삿말 추가 실패: {e}")

    async def delete_greeting_cache(self, channel_id: str, keyword: str):
        """인삿말 하나를 Redis에서 삭제합니다."""
        cache_key = f"greetings:{channel_id}"
        try:
            if await redis_client.exists(cache_key):
                await redis_client.hdel(cache_key, keyword)
        except Exception as e:
            print(f"⚠️ Redis 인삿말 삭제 실패: {e}")

    async def check_and_set_cooldown(self, channel_id: str, command: str, cooldown_seconds: int) -> bool:
        """
        쿨타임 체크 및 설정.
        쿨타임 중이면 True 반환, 아니면 쿨타임 설정 후 False 반환.
        """
        if cooldown_seconds <= 0:
            return False
            
        cache_key = f"cooldown:{channel_id}:{command}"
        
        try:
            if await redis_client.get(cache_key):
                return True
            
            await redis_client.set(cache_key, "1", ex=cooldown_seconds)
            return False
        except Exception as e:
            print(f"⚠️ Redis 쿨타임 체크 실패: {e}")
            return False # 에러 시 쿨타임 없이 실행 허용