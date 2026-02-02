from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.tunnel import tunnel
from app.api.auth import auth
from app.api import routes_chat


# api
app = FastAPI(title="milkyway bot")
app.include_router(auth.auth_router, prefix="/auth", tags=["auth"])
# app.include_router(routes_chat.router, prefix="/chat", tags=["chat"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load the ML model
    print("milky way bot 시작!")
    yield
    # Clean up the ML models and release the resources
    print("milky way bot 종료!")
    tunnel.stop()

@app.get("/")
async def root():
    return {"status": "ok", "service": "milkyway-bot"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "milkywaybot"}