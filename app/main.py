from fastapi import FastAPI

from app.db.database import lifespan
from app.db.tunnel import tunnel
from app.api.auth import auth_router


# api
app = FastAPI(
    lifespan=lifespan,
    title="milkyway bot"
    )
app.include_router(auth_router.auth_router)
# app.include_router(routes_chat.router, prefix="/chat", tags=["chat"])


@app.get("/")
async def root():
    return {"status": "ok", "service": "milkyway-bot"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "milkywaybot"}