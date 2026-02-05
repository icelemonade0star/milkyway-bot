import os

from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db.tunnel import ParamikoTunnel

tunnel = ParamikoTunnel()  # 싱글톤 인스턴스

@asynccontextmanager
async def lifespan(app: FastAPI):
    # STARTUP: SSH 터널 자동 시작
    print("🚀 서버 시작 - SSH 터널 초기화")
    
    # DB 엔진 생성 (싱글톤 터널 사용)
    DATABASE_URL = f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@localhost:{tunnel.local_port}/{os.getenv('DB_NAME')}"
    engine = create_engine(DATABASE_URL, pool_size=10, max_overflow=20, pool_pre_ping=True)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    # 전역 변수로 저장
    app.state.engine = engine
    app.state.SessionLocal = SessionLocal
    app.state.tunnel = tunnel
    
    yield
    
    # SHUTDOWN: 자동 정리
    SessionLocal.close_all()
    engine.dispose()
    tunnel.stop()
    print("🔒 모든 연결 종료")

def get_db(request: FastAPI = Depends()):
    db = request.state.SessionLocal()
    try:
        yield db
    finally:
        db.close()