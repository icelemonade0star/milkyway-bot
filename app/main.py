from fastapi import FastAPI
from app.lifespan import lifespan
from app.features.auth.router import auth_router
from app.features.chat.router import chat_router
from app.features.guide.router import guide_router


# api
app = FastAPI(
    lifespan=lifespan,
    title="milkyway bot",
    version = "1.0.1",
    docs_url = "/swagger",
    description = "밀키웨이 봇 API 문서입니다."
    )
app.include_router(auth_router.auth_router)
app.include_router(chat_router.chat_router)
app.include_router(guide_router.guide_router)

@app.get("/")
async def root():
    return {"status": "ok", "service": "milkyway-bot"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "milkywaybot"}
