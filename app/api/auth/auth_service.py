from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from datetime import datetime, timedelta
from fastapi import HTTPException
from app.db.query_loader import query_loader

class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def save_chzzk_auth(self, chzzk_auth):
        """
        치지직 인증 정보를 DB에 저장하고 결과를 반환합니다.
        """
        # 1. 쿼리 로드
        insert_query_obj = query_loader.get_query("auth_token_insert")

        # 파라미터 딕셔너리 구성
        params = {
            "channel_id": chzzk_auth.channel_id,
            "channel_name": chzzk_auth.channel_name,
            "access_token": chzzk_auth.access_token,
            "refresh_token": chzzk_auth.refresh_token
        }

        try:
            # 2. 쿼리 실행
            result = await self.db.execute(insert_query_obj, params)
            
            inserted_data = result.fetchone()
            await self.db.commit()
            
            return inserted_data

        except Exception as e:
            # 에러 발생 시 롤백
            await self.db.rollback()
            print(f"[DB Error] {str(e)}")
            raise HTTPException(status_code=500, detail="DB 저장 중 오류가 발생했습니다.")

    async def get_auth_list(self, channel_name: str = None):
        # 1. LIKE 검색을 위한 패턴 생성
        search_pattern = f"%{channel_name}%" if channel_name else None
        
        # 2. 쿼리 로드
        query_obj = query_loader.get_query("auth_token_list")

        params = {
            "channel_name": channel_name,
            "channel_name_like": search_pattern
        }
        
        try:
            result = await self.db.execute(query_obj, params)
            # 3. 모든 결과 가져오기
            return result.fetchall()
        except Exception as e:
            print(f"[DB Error] List fetch failed: {str(e)}")
            return []
        

    async def get_auth_token_by_id(self, channel_id: str = None):
        #쿼리 로드
        query_obj = query_loader.get_query("get_auth_token_by_id")

        try:
            result = await self.db.execute(query_obj, {"channel_id": channel_id})
            # 하나의 결과 가져오기
            row = result.fetchone()
        
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
        query_obj = query_loader.get_query("auth_token_update")
        params = {
            "channel_id": channel_id,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": expires_at
        }
        await self.db.execute(query_obj, params)
        await self.db.commit()
