import redis.asyncio as redis
from datetime import timedelta

from app.api.chat.chat_service import ChatService

redis_client = redis.Redis(host="redis", port=6379, decode_responses=True)

class RedisConfigService:
    def __init__(self, chat_service: ChatService):
        self.chat_service = chat_service

    @staticmethod
    def get_cache_key(channel_id: str):
        return f"config:prefix:{channel_id}"

    async def get_command_prefix(self, channel_id: str) -> str:
        
        cache_key = self.get_cache_key(channel_id)
        
        # 1. Redis에서 조회
        prefix = await redis_client.get(cache_key)
        if prefix:
            return prefix
        
        # 2. Redis에 없으면 DB에서 조회
        config_data = await self.chat_service.get_channel_config(channel_id)

        if config_data and hasattr(config_data, 'command_prefix'):
            db_prefix = config_data.command_prefix

            # 3. 조회한 데이터를 Redis에 적재
            await redis_client.set(cache_key, db_prefix, ex=timedelta(days=1))
            return db_prefix
        
        # 4. DB에도 정보가 없다면 기본값 반환
        return "!"

    async def update_command_prefix(self, channel_id: str, new_prefix: str, language: str = "ko", is_active: bool = True):
        # 1. DB 업데이트
        await self.chat_service.update_channel_config(
            channel_id=channel_id, 
            command_prefix=new_prefix, 
            language=language, 
            is_active=is_active
        )
        
        # 2. Redis 캐시 갱신
        cache_key = self.get_cache_key(channel_id)
        await redis_client.set(cache_key, new_prefix, ex=timedelta(days=1))