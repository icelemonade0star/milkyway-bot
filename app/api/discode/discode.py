import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from app.api.discode.chzzk_notifications import ChzzkNotification 

load_dotenv()
discord_token = os.getenv("DISCORD_TOKEN")

bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())

@bot.event
async def on_ready():
    print(f"Milkyway Bot ({bot.user}) 로그인 완료!")

if __name__ == "__main__":
    if discord_token:
        bot.run(discord_token)
    else:
        print("Error: DISCORD_TOKEN not found in environment variables.")