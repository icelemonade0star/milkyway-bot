from fastapi import Depends

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from app.db.models import AuthToken, ChannelConfig, StreamSession, ChzzkNotification

from app.core.database import get_async_db


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def save_chzzk_auth(self, chzzk_auth):
        """
        치지직 인증 정보를 DB에 저장하고 결과를 반환합니다.
        """
        try:
            # 1. AuthToken 저장 (Merge는 없으면 Insert, 있으면 Update를 수행)
            token_model = await self.db.merge(AuthToken(
                channel_id=chzzk_auth.channel_id,
                channel_name=chzzk_auth.channel_name,
                access_token=chzzk_auth.access_token,
                refresh_token=chzzk_auth.refresh_token,
                expires_at=chzzk_auth.expires_at
            ))
            
            # 2. 채널 설정 초기값 생성 (이미 존재하면 무시)
            # get으로 먼저 확인
            config_exists = await self.db.get(ChannelConfig, chzzk_auth.channel_id)
            if not config_exists:
                new_config = ChannelConfig(channel_id=chzzk_auth.channel_id)
                self.db.add(new_config)

            await self.db.commit()
            
            # merge된 객체는 세션에 연결되어 있으므로 바로 반환 가능
            return token_model

        except Exception as e:
            # 에러 발생 시 롤백
            await self.db.rollback()
            print(f"[DB Error] {str(e)}")
            raise HTTPException(status_code=500, detail="DB 저장 중 오류가 발생했습니다.")

    async def get_auth_list(self, channel_name: str = None):
        # ORM 스타일 조회
        stmt = select(AuthToken)
        
        if channel_name:
            stmt = stmt.where(AuthToken.channel_name.like(f"%{channel_name}%"))
        
        try:
            result = await self.db.execute(stmt)
            return result.scalars().all() # 객체 리스트 반환
        except Exception as e:
            print(f"[DB Error] List fetch failed: {str(e)}")
            return []
        
    async def get_auth_token_by_id(self, channel_id: str = None):
        try:
            # 기본 키로 조회할 때는 get()이 가장 빠르고 간편합니다.
            row = await self.db.get(AuthToken, channel_id)
        
            if not row:
                print(f"⚠️ [DB] 해당 ID의 토큰이 없습니다: {channel_id}")
                return None
                
            return row
        except Exception as e:
            print(f"[DB Error] List fetch failed: {str(e)}")
            return None
        
    async def update_auth_token(self, channel_id: str, data: dict):
        
        new_access_token = data.get("accessToken")
        new_refresh_token = data.get("refreshToken")
        expires_in = data.get("expiresIn", 86400) # 기본값 1일(86400초)
        
        # 만료 시간 계산
        new_expires_at = datetime.now() + timedelta(seconds=expires_in)

        if not new_access_token:
            print(f"❌ 업데이트 실패: 응답에 accessToken이 없습니다. (Data: {data})")
            return None

        # 3. DB 업데이트 (여기에 UPDATE 쿼리가 필요합니다)
        await self.update_token(
            channel_id=channel_id,
            access_token=new_access_token,
            refresh_token=new_refresh_token,
            expires_at=new_expires_at
        )
        return new_access_token
    
    async def update_token(self, channel_id, access_token, refresh_token, expires_at):
        stmt = (
            update(AuthToken)
            .where(AuthToken.channel_id == channel_id)
            .values(access_token=access_token, refresh_token=refresh_token, expires_at=expires_at)
        )
        
        await self.db.execute(stmt)
        await self.db.commit()

    async def delete_auth_token(self, channel_id: str):
        stmt = delete(AuthToken).where(AuthToken.channel_id == channel_id)
        try:
            await self.db.execute(stmt)
            await self.db.commit()
            return True
        except Exception as e:
            await self.db.rollback()
            print(f"[DB Error] Token delete failed: {str(e)}")
            return False

    async def cleanup_inactive_channels(self, days: int = 30) -> list[str]:
        """비활성 채널의 인증 정보를 삭제합니다. 반환: 삭제된 channel_id 목록

        삭제 대상:
        - 스트림 기록 있음 + 가장 최근 방송이 {days}일 초과
        - 스트림 기록 없음 + 인증 등록일이 {days}일 초과 (방치된 신규 등록)
        """
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)

            # Case 1: 스트림 기록 있음 + 최근 방송이 cutoff 이전
            case1 = (
                select(AuthToken.channel_id)
                .join(StreamSession, AuthToken.channel_id == StreamSession.chzzk_channel_id)
                .group_by(AuthToken.channel_id)
                .having(func.max(StreamSession.opened_at) < cutoff)
            )

            # Case 2: 스트림 기록 없음 + 등록일이 cutoff 이전
            stream_exists = (
                select(StreamSession.chzzk_channel_id)
                .where(StreamSession.chzzk_channel_id == AuthToken.channel_id)
                .correlate(AuthToken)
                .exists()
            )
            case2 = (
                select(AuthToken.channel_id)
                .where(AuthToken.created_at < cutoff)
                .where(~stream_exists)
            )

            from sqlalchemy import union
            combined = union(case1, case2).subquery()
            result = await self.db.execute(select(combined.c.channel_id))
            inactive_ids = result.scalars().all()

            if not inactive_ids:
                return []

            # StreamSession 삭제 — 재등록 시 과거 기록으로 오탐 방지 (FK 없어서 명시적 삭제)
            await self.db.execute(
                delete(StreamSession).where(StreamSession.chzzk_channel_id.in_(inactive_ids))
            )
            # ChzzkNotification 삭제 (FK 없어서 CASCADE 안 됨)
            await self.db.execute(
                delete(ChzzkNotification).where(ChzzkNotification.chzzk_channel_id.in_(inactive_ids))
            )
            # AuthToken 삭제 → ChannelConfig, ChatCommand, ChatGreeting, Attendance CASCADE 삭제
            await self.db.execute(
                delete(AuthToken).where(AuthToken.channel_id.in_(inactive_ids))
            )
            await self.db.commit()

            # Redis 캐시 정리 (실패해도 DB 삭제는 이미 완료됐으므로 무시)
            try:
                from app.redis.redis_service import redis_client
                keys_to_delete = []
                for ch_id in inactive_ids:
                    keys_to_delete += [
                        f"greetings:{ch_id}",
                        f"config:prefix:{ch_id}",
                        f"live_status:{ch_id}",
                    ]
                if keys_to_delete:
                    await redis_client.delete(*keys_to_delete)
            except Exception as e:
                print(f"[Cleanup] Redis 캐시 정리 실패 (무시): {e}")

            return list(inactive_ids)

        except Exception as e:
            await self.db.rollback()
            print(f"[Cleanup] 비활성 채널 정리 중 오류 발생: {e}")
            return []


async def get_auth_service(db: AsyncSession = Depends(get_async_db)):
    return AuthService(db)