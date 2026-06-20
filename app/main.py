from fastapi import FastAPI
from fastapi import Request

from app.lifespan import lifespan
from app.exception_handlers import register_exception_handlers
from app.features.auth import router as auth_router
from app.features.chat import router as chat_router
from app.features.guide import router as guide_router
from app.features.dashboard.router import dashboard_router
from app.features.admin.router import admin_router


app = FastAPI(
    lifespan=lifespan,
    title="milkyway bot",
    version="1.4.0",
    docs_url="/api/swagger",
    description="밀키웨이 봇 API 문서입니다.",
)
register_exception_handlers(app)
app.include_router(auth_router.auth_router)
app.include_router(chat_router.chat_router)
app.include_router(guide_router.guide_router)
app.include_router(dashboard_router)
app.include_router(admin_router)


@app.middleware("http")
async def add_noindex_header_for_auth_routes(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/auth"):
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


@app.get("/")
async def root():
    return {"status": "ok", "service": "milkyway-bot"}


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "milkywaybot"}
