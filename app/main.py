from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, Query
from sqlalchemy.orm import Session

from app.db.database import lifespan, get_db
from app.db.tunnel import tunnel
from app.api.auth import auth
from app.api import routes_chat


# api
app = FastAPI(
    lifespan=lifespan,
    title="milkyway bot"
    )
app.include_router(auth.auth_router)
# app.include_router(routes_chat.router, prefix="/chat", tags=["chat"])


@app.get("/")
async def root():
    return {"status": "ok", "service": "milkyway-bot"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "milkywaybot"}