from fastapi import Depends

from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from app.db.query_loader import query_loader
from app.db.database import get_async_db

class ChatService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def set_channel_config(self, channel_id: str):
        """
        채널 설정 정보를 DB에 저장하는 메서드
        """
        # 1. 쿼리 로드
        insert_query_obj = query_loader.get_query("channel_config_insert")

        try:
            # 2. 쿼리 실행
            result = await self.db.execute(insert_query_obj, {"channel_id": channel_id})
            
            inserted_data = result.fetchone()
            await self.db.commit()
            
            return inserted_data

        except Exception as e:
            # 에러 발생 시 롤백
            await self.db.rollback()
            print(f"[DB Error] {str(e)}")
            raise HTTPException(status_code=500, detail="DB 저장 중 오류가 발생했습니다.")
        
    async def update_channel_config(self, channel_id: str, command_prefix: str, language: str, is_active: bool):
        """
        채널 설정 정보를 DB에 업데이트하는 메서드
        """
        # 1. 쿼리 로드
        update_query_obj = query_loader.get_query("channel_config_insert_update")

        params = {
            "channel_id": channel_id,
            "command_prefix": command_prefix,
            "language": language,
            "is_active": is_active
        }

        try:
            # 2. 쿼리 실행
            result = await self.db.execute(update_query_obj, params)
            
            updated_data = result.fetchone()
            await self.db.commit()
            
            return updated_data

        except Exception as e:
            # 에러 발생 시 롤백
            await self.db.rollback()
            print(f"[DB Error] {str(e)}")
            raise HTTPException(status_code=500, detail="DB 업데이트 중 오류가 발생했습니다.")

    async def get_channel_config(self, channel_id: str):
        """
        채널 설정 정보를 DB에서 조회하는 메서드
        """
        # 1. 쿼리 로드
        query_obj = query_loader.get_query("get_channel_config_by_id")

        try:
            # 2. 쿼리 실행
            result = await self.db.execute(query_obj, {"channel_id": channel_id})
            
            config_data = result.fetchone()
            return config_data

        except Exception as e:
            print(f"[DB Error] {str(e)}")
            raise HTTPException(status_code=500, detail="DB 조회 중 오류가 발생했습니다.")
        
    async def get_global_commands(self, command: str):
        """
        채널 설정 정보를 DB에서 조회하는 메서드
        """
        # 1. 쿼리 로드
        query_obj = query_loader.get_query("get_global_chat_commands_by_command")

        try:
            # 2. 쿼리 실행
            result = await self.db.execute(query_obj, {"command": command})
            
            config_data = result.fetchone()
            return config_data

        except Exception as e:
            print(f"[DB Error] {str(e)}")
            raise HTTPException(status_code=500, detail="DB 조회 중 오류가 발생했습니다.")
        
async def get_chat_service(db: AsyncSession = Depends(get_async_db)):
    return ChatService(db)

   