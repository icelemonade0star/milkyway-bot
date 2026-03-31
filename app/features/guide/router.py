from fastapi import APIRouter
from fastapi.responses import HTMLResponse
import os

guide_router = APIRouter(tags=["guide"])

@guide_router.get("/guide", response_class=HTMLResponse)
async def get_guide():
    # Get the directory of the current file
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # Construct the path to the template file
    template_path = os.path.join(current_dir, '..', '..', 'templates', 'guide.html')
    
    try:
        with open(template_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
        return HTMLResponse(content=html_content)
    except FileNotFoundError:
        return HTMLResponse(content="<h1>404 - 가이드 파일을 찾을 수 없습니다.</h1>", status_code=404)