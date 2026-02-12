from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from app.db.query_loader import query_loader

class ChatService:
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

   