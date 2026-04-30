from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from app.core.config import TEMPLATE_DIR

guide_router = APIRouter(tags=["guide"])

# FastAPI의 표준 템플릿 렌더링 방식을 사용합니다.
# 템플릿 디렉터리 경로는 config 파일에서 가져옵니다.
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

@guide_router.get("/guide", response_class=HTMLResponse)
async def get_guide(request: Request):
    # templates.TemplateResponse를 사용하여 HTML 파일을 렌더링합니다.
    # {"request": request}는 Jinja2 템플릿에 필수적으로 전달해야 하는 컨텍스트입니다.
    return templates.TemplateResponse("guide.html", {"request": request})