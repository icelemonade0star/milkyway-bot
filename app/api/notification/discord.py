import os
import logging
import discord
from discord.ext import commands
from dotenv import load_dotenv
from app.api.notification.chzzk_notifications import ChzzkNotification

load_dotenv()
discord_token = os.getenv("DISCORD_TOKEN")

bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())

@bot.event
async def on_ready():
    print(f"Milkyway Bot ({bot.user}) 로그인 완료!")


async def start_discord_bot(token: str):
    try:
        # discord.py 내부 통신 로그 켜기
        discord.utils.setup_logging(level=logging.INFO)

        await bot.add_cog(ChzzkNotification(bot))
        
        print("⏳ [Discord] 서버로 연결 시도 중...")
        await bot.start(token)
        
    except Exception as e:
        print(f"🚨 [Discord] 봇 실행 중 치명적 에러 발생: {e}")

if __name__ == "__main__":
    if discord_token:
        bot.run(discord_token)
    else:
        print("Error: DISCORD_TOKEN not found in environment variables.")