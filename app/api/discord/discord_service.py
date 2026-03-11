import discord
import logging
from typing import Optional, Union

# 기존에 정의된 봇 인스턴스 가져오기
from app.api.notification.discord import bot

class DiscordService:
    def __init__(self):
        self.logger = logging.getLogger("DiscordService")

    async def send_message(self, channel_id: Union[str, int], message: str, embed: Optional[discord.Embed] = None) -> bool:
        """
        디스코드 채널 ID로 메시지를 전송합니다.
        
        Args:
            channel_id (Union[str, int]): 디스코드 채널 ID
            message (str): 보낼 텍스트 메시지
            embed (Optional[discord.Embed]): (선택) 임베드 객체

        Returns:
            bool: 전송 성공 여부
        """
        if not bot.is_ready():
            self.logger.warning("봇이 아직 준비되지 않았습니다. (Login Pending)")
            return False

        try:
            # 1. ID 정수 변환
            target_id = int(channel_id)
            
            # 2. 채널 조회 (캐시 -> API 순서)
            channel = bot.get_channel(target_id)
            
            if not channel:
                self.logger.debug(f"캐시에서 채널({target_id})을 찾을 수 없음. API 조회 시도...")
                try:
                    channel = await bot.fetch_channel(target_id)
                except discord.NotFound:
                    self.logger.error(f"채널({target_id})이 존재하지 않습니다.")
                    return False
                except discord.Forbidden:
                    self.logger.error(f"채널({target_id})에 접근할 권한이 없습니다.")
                    return False

            # 3. 메시지 전송
            if channel:
                # 텍스트 채널인지 확인 (send 메서드가 있는지)
                if hasattr(channel, 'send'):
                    await channel.send(content=message, embed=embed)
                    self.logger.info(f"메시지 전송 성공: {channel.name} ({target_id})")
                    return True
                else:
                    self.logger.error(f"해당 채널({target_id})은 텍스트를 보낼 수 없는 유형입니다.")
                    return False

        except ValueError:
            self.logger.error(f"유효하지 않은 채널 ID 형식입니다: {channel_id}")
            return False
        except discord.Forbidden:
            self.logger.error(f"채널({channel_id})에 메시지를 보낼 권한이 없습니다.")
            return False
        except Exception as e:
            self.logger.error(f"메시지 전송 중 알 수 없는 에러 발생: {e}")
            return False
