from fastapi import Request
from sqlalchemy.ext.asyncio import create_async_engine
import app.core.config as config

AsyncSessionLocal = None

async def get_async_db(request: Request):
    async with request.app.state.SessionLocal() as db:
        try:
            yield db
            # commit은 컨트롤러(router)에서 명시적으로 하거나 여기서 처리
        finally:
            await db.close()

def get_session_factory():
    return AsyncSessionLocal

def create_db_engine(local_port):
    # 터널링 포트가 있으면 localhost 사용, 없으면 설정된 DB_HOST 사용
    db_host = "localhost" if local_port and config.SSH_HOST else config.DB_HOST
    # 포트가 명시적으로 넘어오면 사용, 아니면 설정된 DB_PORT 사용
    db_port = local_port if local_port else config.DB_PORT
    
    DATABASE_URL = f"postgresql+asyncpg://{config.DB_USER}:{config.DB_PASSWORD}@{db_host}:{db_port}/{config.DB_NAME}"
    return create_async_engine(
        DATABASE_URL,
        pool_size=3,         # 1GB 서버 환경: 커넥션 3개로 충분 (각 ~5-10MB)
        max_overflow=2,      # 순간 트래픽 대비 최대 5개까지 허용
        pool_recycle=3600,   # SSH 터널 특성상 끊김 방지를 위해 1시간마다 커넥션 재사용
        pool_pre_ping=True,
        echo=False           # SQL 로그가 필요하면 True
    )