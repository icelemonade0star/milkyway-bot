from fastapi import Request
from sqlalchemy.ext.asyncio import create_async_engine
import app.config as config

AsyncSessionLocal = None

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

def create_db_engine(local_port):
    DATABASE_URL = f"postgresql+asyncpg://{config.DB_USER}:{config.DB_PASSWORD}@localhost:{local_port}/{config.DB_NAME}"
    return create_async_engine(
        DATABASE_URL, 
        pool_size=10,       # 챗봇 동시 접속자가 많다면 조금 늘려주세요
        max_overflow=0, 
        pool_recycle=3600,   # SSH 터널 특성상 끊김 방지를 위해 1시간마다 커넥션 재사용
        pool_pre_ping=True,
        echo=False # SQL 로그가 필요하면 True
    )