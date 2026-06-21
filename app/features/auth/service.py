from dataclasses import dataclass
import logging

from fastapi import Depends

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from app.db import models

from app.core.database import get_async_db

logger = logging.getLogger("AuthService")


def _invalidate_redis_channel_key(platform: str, platform_channel_id: str):
    try:
        from app.redis.redis_service import RedisConfigService

        RedisConfigService.invalidate_channel_key(platform, platform_channel_id)
    except Exception as e:
        logger.warning("Redis channel key invalidation failed: %s", e)


@dataclass
class PlatformAuthRecord:
    channel_id: str
    channel_name: str
    access_token: str | None
    refresh_token: str | None
    expires_at: datetime | None
    created_at: datetime | None = None
    updated_at: datetime | None = None

class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_v2_channel_by_platform_id(self, platform: str, platform_channel_id: str):
        stmt = select(models.V2Channel).where(
            models.V2Channel.platform == platform,
            models.V2Channel.platform_channel_id == platform_channel_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def save_platform_auth(
        self,
        *,
        platform: str,
        platform_channel_id: str,
        channel_name: str,
        access_token: str | None,
        refresh_token: str | None,
        expires_at,
        token_type: str | None = None,
        scope: str | None = None,
        raw_token_response: dict | None = None,
        profile_image_url: str | None = None,
    ):
        channel = await self.get_v2_channel_by_platform_id(platform, platform_channel_id)
        if not channel:
            channel = models.V2Channel(
                platform=platform,
                platform_channel_id=platform_channel_id,
                channel_name=channel_name,
                profile_image_url=profile_image_url,
                is_active=True,
            )
            self.db.add(channel)
            await self.db.flush()
        else:
            channel.channel_name = channel_name
            if profile_image_url is not None:
                channel.profile_image_url = profile_image_url
            channel.is_active = True

        config_exists = await self.db.get(models.V2ChannelConfig, channel.id)
        if not config_exists:
            self.db.add(models.V2ChannelConfig(channel_id=channel.id))

        stmt = select(models.V2PlatformCredential).where(
            models.V2PlatformCredential.channel_id == channel.id,
            models.V2PlatformCredential.platform == platform,
        )
        credential = (await self.db.execute(stmt)).scalar_one_or_none()
        if not credential:
            credential = models.V2PlatformCredential(
                channel_id=channel.id,
                platform=platform,
            )
            self.db.add(credential)

        credential.access_token = access_token
        credential.refresh_token = refresh_token
        credential.expires_at = expires_at
        credential.token_type = token_type
        credential.scope = scope
        credential.raw_token_response = raw_token_response

        return channel

    async def save_default_platform_auth(self, platform_auth):
        """
        기본 플랫폼 인증 정보를 DB에 저장하고 결과를 반환합니다.
        """
        try:
            platform = getattr(platform_auth, "platform", None)
            if not platform:
                raise ValueError("platform_auth.platform is required")

            channel = await self.save_platform_auth(
                platform=platform,
                platform_channel_id=platform_auth.channel_id,
                channel_name=platform_auth.channel_name,
                access_token=platform_auth.access_token,
                refresh_token=platform_auth.refresh_token,
                expires_at=platform_auth.expires_at,
                raw_token_response=getattr(platform_auth, "raw_token_response", None),
            )
            await self.db.commit()
        except Exception as e:
            await self.db.rollback()
            logger.error("save_default_platform_auth failed: %s", e)
            raise HTTPException(status_code=500, detail="DB 저장 중 오류가 발생했습니다.")

        _invalidate_redis_channel_key(platform, platform_auth.channel_id)

        return PlatformAuthRecord(
            channel_id=channel.platform_channel_id,
            channel_name=channel.channel_name,
            access_token=platform_auth.access_token,
            refresh_token=platform_auth.refresh_token,
            expires_at=platform_auth.expires_at,
            created_at=channel.created_at,
            updated_at=channel.updated_at,
        )

    async def get_auth_list(self, platform: str, channel_name: str | None = None):
        stmt = (
            select(models.V2Channel, models.V2PlatformCredential)
            .outerjoin(
                models.V2PlatformCredential,
                (models.V2PlatformCredential.channel_id == models.V2Channel.id)
                & (models.V2PlatformCredential.platform == models.V2Channel.platform),
            )
            .where(models.V2Channel.platform == platform)
        )
        
        if channel_name:
            stmt = stmt.where(models.V2Channel.channel_name.like(f"%{channel_name}%"))
        
        try:
            result = await self.db.execute(stmt)
            return [
                PlatformAuthRecord(
                    channel_id=channel.platform_channel_id,
                    channel_name=channel.channel_name,
                    access_token=credential.access_token if credential else None,
                    refresh_token=credential.refresh_token if credential else None,
                    expires_at=credential.expires_at if credential else None,
                    created_at=channel.created_at,
                    updated_at=channel.updated_at,
                )
                for channel, credential in result.all()
            ]
        except Exception as e:
            logger.error("Auth list fetch failed: %s", e)
            return []
        
    async def get_auth_token_by_id(self, platform: str, channel_id: str | None = None):
        try:
            stmt = (
                select(models.V2Channel, models.V2PlatformCredential)
                .outerjoin(
                    models.V2PlatformCredential,
                    (models.V2PlatformCredential.channel_id == models.V2Channel.id)
                    & (models.V2PlatformCredential.platform == models.V2Channel.platform),
                )
                .where(
                    models.V2Channel.platform == platform,
                    models.V2Channel.platform_channel_id == channel_id,
                )
            )
            row = (await self.db.execute(stmt)).one_or_none()
        
            if not row:
                logger.warning("Auth token not found: channel_id=%s", channel_id)
                return None
                
            channel, credential = row
            return PlatformAuthRecord(
                channel_id=channel.platform_channel_id,
                channel_name=channel.channel_name,
                access_token=credential.access_token if credential else None,
                refresh_token=credential.refresh_token if credential else None,
                expires_at=credential.expires_at if credential else None,
                created_at=channel.created_at,
                updated_at=channel.updated_at,
            )
        except Exception as e:
            logger.error("Auth token fetch failed: %s", e)
            return None
        
    async def update_auth_token(self, platform: str, channel_id: str, data: dict):
        
        new_access_token = data.get("accessToken")
        new_refresh_token = data.get("refreshToken")
        expires_in = data.get("expiresIn", 86400) # 기본값 1일(86400초)
        
        # 만료 시간 계산
        new_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        if not new_access_token:
            logger.warning("Token update failed: accessToken missing. data=%s", data)
            return None

        # 3. DB 업데이트 (여기에 UPDATE 쿼리가 필요합니다)
        await self.update_token(
            platform=platform,
            channel_id=channel_id,
            access_token=new_access_token,
            refresh_token=new_refresh_token,
            expires_at=new_expires_at
        )
        return new_access_token
    
    async def update_token(self, platform, channel_id, access_token, refresh_token, expires_at):
        v2_channel = await self.get_v2_channel_by_platform_id(platform, channel_id)
        if v2_channel:
            stmt_v2 = (
                update(models.V2PlatformCredential)
                .where(
                    models.V2PlatformCredential.channel_id == v2_channel.id,
                    models.V2PlatformCredential.platform == platform,
                )
                .values(
                    access_token=access_token,
                    refresh_token=refresh_token,
                    expires_at=expires_at,
                )
            )
            await self.db.execute(stmt_v2)

        await self.db.commit()

    async def delete_auth_token(self, platform: str, channel_id: str):
        try:
            v2_channel = await self.get_v2_channel_by_platform_id(platform, channel_id)
            if v2_channel:
                await self.db.delete(v2_channel)
            await self.db.commit()
        except Exception as e:
            await self.db.rollback()
            logger.error("Token delete failed: %s", e)
            return False

        _invalidate_redis_channel_key(platform, channel_id)
        return True

    async def cleanup_inactive_channels(self, platform: str, days: int = 30) -> list[str]:
        """비활성 채널의 인증 정보를 삭제합니다. 반환: 삭제된 channel_id 목록

        삭제 대상:
        - 스트림 기록 있음 + 가장 최근 방송이 {days}일 초과
        - 스트림 기록 없음 + 인증 등록일이 {days}일 초과 (방치된 신규 등록)
        """
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)

            # Case 1: 스트림 기록 있음 + 최근 방송이 cutoff 이전
            case1 = (
                select(models.V2Channel.platform_channel_id)
                .join(models.V2StreamSession, models.V2Channel.id == models.V2StreamSession.channel_id)
                .where(models.V2Channel.platform == platform)
                .group_by(models.V2Channel.id)
                .having(func.max(models.V2StreamSession.opened_at) < cutoff)
            )

            # Case 2: 스트림 기록 없음 + 등록일이 cutoff 이전
            stream_exists = (
                select(models.V2StreamSession.channel_id)
                .where(models.V2StreamSession.channel_id == models.V2Channel.id)
                .correlate(models.V2Channel)
                .exists()
            )
            case2 = (
                select(models.V2Channel.platform_channel_id)
                .where(models.V2Channel.platform == platform)
                .where(models.V2Channel.created_at < cutoff)
                .where(~stream_exists)
            )

            from sqlalchemy import union
            combined = union(case1, case2).subquery()
            result = await self.db.execute(select(combined.c.channel_id))
            inactive_ids = result.scalars().all()

            if not inactive_ids:
                return []

            inactive_channels = (await self.db.execute(
                select(models.V2Channel).where(
                    models.V2Channel.platform == platform,
                    models.V2Channel.platform_channel_id.in_(inactive_ids),
                )
            )).scalars().all()

            await self.db.execute(
                delete(models.V2Channel).where(
                    models.V2Channel.platform == platform,
                    models.V2Channel.platform_channel_id.in_(inactive_ids),
                )
            )
            await self.db.commit()

            for channel_id in inactive_ids:
                _invalidate_redis_channel_key(platform, channel_id)

            # Redis 캐시 정리 (실패해도 DB 삭제는 이미 완료됐으므로 무시)
            try:
                from app.redis.redis_service import RedisChannelKey, RedisConfigService, redis_client

                keys_to_delete = []
                for channel in inactive_channels:
                    redis_channel = RedisChannelKey(
                        channel.platform,
                        channel.platform_channel_id,
                        str(channel.id),
                    )
                    keys_to_delete += [
                        RedisConfigService.get_greetings_key(redis_channel),
                        RedisConfigService.get_prefix_key(redis_channel),
                        RedisConfigService.get_live_status_key(redis_channel),
                    ]
                if keys_to_delete:
                    await redis_client.delete(*keys_to_delete)
            except Exception as e:
                logger.warning("Cleanup Redis cache failed; ignoring: %s", e)

            return list(inactive_ids)

        except Exception as e:
            await self.db.rollback()
            logger.error("Inactive channel cleanup failed: %s", e)
            return []


async def get_auth_service(db: AsyncSession = Depends(get_async_db)):
    return AuthService(db)
