from fastapi import FastAPI

from app.lifespan import lifespan
from app.features.auth import router as auth_router
from app.features.chat import router as chat_router
from app.features.guide import router as guide_router
from app.features.admin.router import admin_router


# api
app = FastAPI(
    lifespan=lifespan,
    title="milkyway bot",
    version = "1.3.0",
    docs_url = "/api/swagger",
    description = "밀키웨이 봇 API 문서입니다."
    )
app.include_router(auth_router.auth_router)
app.include_router(chat_router.chat_router)
app.include_router(guide_router.guide_router)
app.include_router(admin_router)

@app.get("/")
async def root():
    return {"status": "ok", "service": "milkyway-bot"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "milkywaybot"}
