from contextlib import asynccontextmanager
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.database import create_db_engine
import app.db.database as db_module
from app.db.tunnel import ParamikoTunnel
from app.api.chat.session_manager import session_manager

# 터널 인스턴스 생성
tunnel = ParamikoTunnel()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- STARTUP ---
    print("🚀 서버 시작")
    
    # 1. SSH 터널 자동 시작
    # tunnel.start() 
    
    # 2. DB 엔진 및 세션 팩토리 초기화
    engine = create_db_engine(tunnel.local_port)
    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    
    # 3. 전역 및 앱 상태 주입
    db_module.AsyncSessionLocal = session_factory
    app.state.SessionLocal = session_factory
    
    yield
    
    # --- SHUTDOWN ---
    print("🔒 리소스 정리 시작")
    await session_manager.close_all()
    await engine.dispose()
    tunnel.stop()
    print("✅ 모든 연결 정상 종료")