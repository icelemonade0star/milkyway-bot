from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from app.api.notification.discord import bot
import discord

discord_router = APIRouter(prefix="/test/discord", tags=["Discord Debug"])

class DiscordTestPayload(BaseModel):
    channel_name: str
    message: str

@discord_router.post("/send")
async def send_test_message(payload: DiscordTestPayload):
    """
    디스코드 메시지 전송 테스트 API
    """
    if not bot.is_ready():
        # 상태 코드를 503(Service Unavailable)으로 변경
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="봇이 아직 준비되지 않았습니다. (Login Pending)"
        )
    
    target_channel = None
    input_val = payload.channel_name.strip()
    search_log = []

    # 1. ID 기반 검색
    if input_val.isdigit():
        channel_id = int(input_val)
        search_log.append(f"🆔 ID 기반 검색 시작: {channel_id}")
        
        target_channel = bot.get_channel(channel_id)
        
        if target_channel:
            search_log.append("✅ 캐시(get_channel)에서 채널 발견")
        else:
            search_log.append("⚠️ 캐시에 없음. API(fetch_channel) 직접 호출 시도...")
            try:
                target_channel = await bot.fetch_channel(channel_id)
                search_log.append("✅ API(fetch_channel) 조회 성공")
            except discord.NotFound:
                search_log.append("❌ NotFound: 해당 ID의 채널이 존재하지 않음")
            except discord.Forbidden:
                search_log.append("❌ Forbidden: 봇이 해당 채널을 볼 권한이 없음")
            except Exception as e:
                search_log.append(f"❌ Error: {str(e)}")

    # 2. 이름 기반 검색 (ID 검색 실패 시)
    if not target_channel:
        search_log.append(f"🔍 이름 기반 검색 시작: '{input_val}'")
        
        # discord.utils 활용: 모든 길드의 모든 채널(음성/공지 포함) 캐시에서 이름이 일치하는 채널 검색
        found_channels = [ch for ch in bot.get_all_channels() if ch.name == input_val]
        
        if found_channels:
            search_log.append(f"✅ 이름이 일치하는 채널 {len(found_channels)}개 발견 (서버: {[ch.guild.name for ch in found_channels]})")
            target_channel = found_channels[0]
            
            if len(found_channels) > 1:
                search_log.append(f"⚠️ 경고: 동명의 채널이 여러 개입니다. 첫 번째 채널({target_channel.guild.name} / {target_channel.id})로 전송합니다.")
        else:
            search_log.append("❌ 이름이 일치하는 채널을 찾을 수 없음")

    # 3. 결과 처리 (실패 시 예외 발생)
    if not target_channel:
        # FastAPI 표준 에러 응답 방식으로 변경
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"reason": "채널을 찾을 수 없습니다.", "debug_log": search_log}
        )

    # 4. 메시지 전송
    try:
        await target_channel.send(payload.message)
        return {
            "status": "success",
            "channel_info": {
                "name": target_channel.name,
                "id": str(target_channel.id),
                "guild": target_channel.guild.name
            },
            "debug_log": search_log
        }
    except discord.Forbidden:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "reason": "채널은 찾았으나 메시지 전송 권한이 없습니다 (Send Messages 권한 필요)",
                "channel_info": {"name": target_channel.name, "id": str(target_channel.id)},
                "debug_log": search_log
            }
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"reason": str(e), "debug_log": search_log}
        )