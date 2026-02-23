from fastapi import FastAPI

from app.lifespan import lifespan
from app.db.tunnel import ParamikoTunnel
from app.api.auth import auth_router
from app.api.chat import chat_router

# api
app = FastAPI(
    lifespan=lifespan,
    title="milkyway bot",
    version = "1.0.0",
    docs_url = "/swagger",
    description = "밀키웨이 봇 API 문서입니다."
    )
app.include_router(auth_router.auth_router)
app.include_router(chat_router.chat_router)


@app.get("/")
async def root():
    return {"status": "ok", "service": "milkyway-bot"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "milkywaybot"}
