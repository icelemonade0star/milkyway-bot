from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from fastapi.templating import Jinja2Templates
from app.core.config import PUBLIC_SITE_URL, TEMPLATE_DIR

guide_router = APIRouter(tags=["guide"])

# FastAPI의 표준 템플릿 렌더링 방식을 사용합니다.
# 템플릿 디렉터리 경로는 config 파일에서 가져옵니다.
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

@guide_router.get("/guide", response_class=HTMLResponse)
async def get_guide(request: Request):
    # templates.TemplateResponse를 사용하여 HTML 파일을 렌더링합니다.
    # {"request": request}는 Jinja2 템플릿에 필수적으로 전달해야 하는 컨텍스트입니다.
    return templates.TemplateResponse(
        "guide.html",
        {
            "request": request,
            "public_site_url": PUBLIC_SITE_URL,
        },
    )


@guide_router.get("/robots.txt", response_class=PlainTextResponse)
async def robots_txt():
    return "\n".join(
        [
            "User-agent: *",
            "Allow: /guide",
            "Disallow: /admin",
            "Disallow: /api",
            "Disallow: /auth/",
            "Disallow: /auth/callback",
            "Disallow: /auth/chzzk/callback",
            "Disallow: /auth/dashboard",
            "Disallow: /auth/dashboard/login",
            f"Sitemap: {PUBLIC_SITE_URL}/sitemap.xml",
            "",
        ]
    )


# Google Search Console HTML 파일 소유권 확인용 엔드포인트입니다.
@guide_router.get("/googleedb72741be7a79c4.html", response_class=PlainTextResponse)
async def google_site_verification():
    return "google-site-verification: googleedb72741be7a79c4.html\n"


@guide_router.get("/sitemap.xml")
async def sitemap_xml():
    content = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>{PUBLIC_SITE_URL}/guide</loc>
    <changefreq>weekly</changefreq>
    <priority>1.0</priority>
  </url>
</urlset>
"""
    return Response(content=content, media_type="application/xml")
