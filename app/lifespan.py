import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.database import create_db_engine
import app.db.database as db_module
from app.db.tunnel import ParamikoTunnel
from app.api.chat.session_manager import session_manager
from app.tasks import token_refresh_task
from app.api.notification.discord import bot, discord_token, start_discord_bot

# 터널 인스턴스 생성
tunnel = ParamikoTunnel()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- STARTUP ---
    print("🚀 서버 시작")
    
    # DB 엔진 및 세션 팩토리 초기화
    engine = create_db_engine(tunnel.local_port)
    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    
    # 전역 및 앱 상태 주입
    db_module.AsyncSessionLocal = session_factory
    app.state.SessionLocal = session_factory

    # 세션 매니저 초기화 및 DB에서 세션 복구 시도
    async with session_factory() as db_session:
        await session_manager.restore_all_sessions_from_db(db_session)
    
    # 토큰 자동 갱신 백그라운드 작업 시작
    refresh_task = asyncio.create_task(token_refresh_task(session_factory))
    
    # 디스코드 봇 백그라운드 실행
    discord_task = None
    if discord_token:
        print("🤖 디스코드 봇 시작")
        discord_task = asyncio.create_task(start_discord_bot(discord_token))
    else:
        print("⚠️ DISCORD_TOKEN이 없어 디스코드 봇을 시작하지 않습니다.")

    yield
    
    # --- SHUTDOWN ---
    print("🔒 리소스 정리 시작")
    # 백그라운드 작업 취소
    refresh_task.cancel()
    if discord_task:
        await bot.close()
    await session_manager.close_all()
    await engine.dispose()
    tunnel.stop()
    print("✅ 모든 연결 정상 종료")