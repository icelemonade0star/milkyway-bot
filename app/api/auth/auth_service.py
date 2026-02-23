from fastapi import Depends

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from datetime import datetime, timedelta
from fastapi import HTTPException
from app.db.models import AuthToken, ChannelConfig

from app.db.database import get_async_db


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
                refresh_token=chzzk_auth.refresh_token
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
        
    async def get_expiring_tokens(self, limit_minutes: int = 30):
        """만료 시간이 limit_minutes 이내로 남은 토큰들을 조회합니다."""
        threshold = datetime.now() + timedelta(minutes=limit_minutes)
        
        stmt = select(AuthToken).where(AuthToken.expires_at <= threshold)
        
        try:
            result = await self.db.execute(stmt)
            return result.scalars().all()
        except Exception as e:
            print(f"[DB Error] Expiring tokens fetch failed: {str(e)}")
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


async def get_auth_service(db: AsyncSession = Depends(get_async_db)):
    return AuthService(db)