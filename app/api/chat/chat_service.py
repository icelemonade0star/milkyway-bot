from fastapi import Depends

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from fastapi import HTTPException
from app.db.models import ChannelConfig, GlobalCommand, ChatCommand
from app.db.database import get_async_db

class ChatService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def set_channel_config(self, channel_id: str):
        """
        채널 설정 정보를 DB에 저장하는 메서드
        """
        try:
            # ORM: 없으면 생성, 있으면 무시 (get_or_create 패턴)
            config = await self.db.get(ChannelConfig, channel_id)
            if not config:
                config = ChannelConfig(channel_id=channel_id)
                self.db.add(config)
                await self.db.commit()
            
            return config

        except Exception as e:
            # 에러 발생 시 롤백
            await self.db.rollback()
            print(f"[DB Error] {str(e)}")
            raise HTTPException(status_code=500, detail="DB 저장 중 오류가 발생했습니다.")
        
    async def update_channel_config(self, channel_id: str, command_prefix: str, language: str, is_active: bool):
        """
        채널 설정 정보를 DB에 업데이트하는 메서드
        """
        try:
            # ORM Update
            stmt = (
                update(ChannelConfig)
                .where(ChannelConfig.channel_id == channel_id)
                .values(command_prefix=command_prefix, language=language, is_active=is_active)
                .execution_options(synchronize_session="fetch") # 현재 세션의 객체도 업데이트
            )
            await self.db.execute(stmt)
            await self.db.commit()
            
            return await self.get_channel_config(channel_id)

        except Exception as e:
            # 에러 발생 시 롤백
            await self.db.rollback()
            print(f"[DB Error] {str(e)}")
            raise HTTPException(status_code=500, detail="DB 업데이트 중 오류가 발생했습니다.")

    async def get_channel_config(self, channel_id: str):
        """
        채널 설정 정보를 DB에서 조회하는 메서드
        """
        try:
            # ORM Get
            config = await self.db.get(ChannelConfig, channel_id)
            return config

        except Exception as e:
            await self.db.rollback()
            print(f"[DB Error] {str(e)}")
            raise HTTPException(status_code=500, detail="DB 조회 중 오류가 발생했습니다.")
        
    async def get_global_commands(self, command: str):
        """
        특정 글로벌 명령어를 DB에서 조회하는 메서드
        """
        try:
            # ORM Select
            stmt = select(GlobalCommand).where(GlobalCommand.command == command)
            result = await self.db.execute(stmt)
            return result.scalar_one_or_none()

        except Exception as e:
            await self.db.rollback()
            print(f"[DB Error] {str(e)}")
            raise HTTPException(status_code=500, detail="DB 조회 중 오류가 발생했습니다.")
        
    async def get_all_global_commands(self):
        """
        활성화된 모든 글로벌 명령어를 조회합니다.
        """
        try:
            stmt = select(GlobalCommand).where(GlobalCommand.is_active == True).order_by(GlobalCommand.display_order.asc())
            result = await self.db.execute(stmt)
            return result.scalars().all()
        except Exception as e:
            await self.db.rollback()
            print(f"[DB Error] {str(e)}")
            return []
            
    async def get_channel_commands(self, channel_id: str):
        """
        특정 채널의 활성화된 커스텀 명령어 목록을 조회합니다.
        """
        try:
            stmt = select(ChatCommand).where(
                ChatCommand.channel_id == channel_id, 
                ChatCommand.is_active == True
            )
            result = await self.db.execute(stmt)
            return result.scalars().all()
        except Exception as e:
            await self.db.rollback()
            print(f"[DB Error] {str(e)}")
            return []
            
    async def get_chat_command(self, channel_id: str, command: str):
        """
        특정 채널의 특정 커스텀 명령어를 조회합니다.
        """
        try:
            stmt = select(ChatCommand).where(
                ChatCommand.channel_id == channel_id, 
                ChatCommand.command == command
            )
            result = await self.db.execute(stmt)
            return result.scalar_one_or_none()
        except Exception as e:
            await self.db.rollback()
            print(f"[DB Error] {str(e)}")
            return None

    async def add_chat_command(self, channel_id: str, command: str, response: str):
        try:
            # 중복 체크
            existing = await self.get_chat_command(channel_id, command)
            if existing:
                return await self.update_chat_command(channel_id, command, response)
            
            # 글로벌 명령어 중복 확인
            global_cmd = await self.get_global_commands(command)
            if global_cmd:
                return False

            new_cmd = ChatCommand(channel_id=channel_id, command=command, response=response)
            self.db.add(new_cmd)
            await self.db.commit()
            return True
        except Exception as e:
            await self.db.rollback()
            print(f"[DB Error] {str(e)}")
            return False

    async def update_chat_command(self, channel_id: str, command: str, response: str):
        try:
            cmd_obj = await self.get_chat_command(channel_id, command)
            if not cmd_obj:
                return False
            
            cmd_obj.response = response
            await self.db.commit()
            return True
        except Exception as e:
            await self.db.rollback()
            print(f"[DB Error] {str(e)}")
            return False

    async def delete_chat_command(self, channel_id: str, command: str):
        try:
            cmd_obj = await self.get_chat_command(channel_id, command)
            if not cmd_obj:
                return False
            
            await self.db.delete(cmd_obj)
            await self.db.commit()
            return True
        except Exception as e:
            await self.db.rollback()
            print(f"[DB Error] {str(e)}")
            return False

async def get_chat_service(db: AsyncSession = Depends(get_async_db)):
    return ChatService(db)

   