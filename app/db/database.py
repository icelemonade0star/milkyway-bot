import os

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.db.tunnel import ParamikoTunnel
from app.api.chat.session_manager import session_manager

tunnel = ParamikoTunnel()  # 싱글톤 인스턴스

AsyncSessionLocal = None



@asynccontextmanager
async def lifespan(app: FastAPI):
    # STARTUP: SSH 터널 자동 시작
    print("🚀 서버 시작 - SSH 터널 초기화")
    global AsyncSessionLocal
    
    # DB 생성
    DATABASE_URL = f"postgresql+asyncpg://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@localhost:{tunnel.local_port}/{os.getenv('DB_NAME')}"    
    
    # 비동기 엔진 생성
    engine = create_async_engine(
        DATABASE_URL, 
        pool_size=10,       # 챗봇 동시 접속자가 많다면 조금 늘려주세요
        max_overflow=0, 
        pool_recycle=3600,   # SSH 터널 특성상 끊김 방지를 위해 1시간마다 커넥션 재사용
        pool_pre_ping=True,
        echo=False # SQL 로그가 필요하면 True
    )

    # 비동기 세션 메이커
    AsyncSessionLocal = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    
    app.state.engine = engine
    app.state.SessionLocal = AsyncSessionLocal
    app.state.tunnel = tunnel
    
    yield
    await session_manager.close_all() # 세션 정리 추가
    # SHUTDOWN: 비동기 엔진 종료
    await engine.dispose()
    tunnel.stop()
    print("🔒 모든 연결 종료")

async def get_async_db(request: Request):
    async with request.app.state.SessionLocal() as db:
        try:
            yield db
            # commit은 컨트롤러(router)에서 명시적으로 하거나 여기서 처리
        finally:
            await db.close()

def get_session_factory():
    global AsyncSessionLocal
    return AsyncSessionLocal