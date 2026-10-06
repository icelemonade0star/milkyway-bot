from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from fastapi.templating import Jinja2Templates
from app.core.config import PUBLIC_SITE_URL, TEMPLATE_DIR
from xml.sax.saxutils import escape

guide_router = APIRouter(tags=["guide"])

templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

GUIDE_PAGES = {
    "": {
        "title": "처음 시작하기", "path": "/guide", "template": "guide.html",
        "description": "밀키웨이 봇을 방송에 연결하고, 필요한 기능의 사용 방법을 확인하세요.",
        "toc": [("start", "설정 순서"), ("features", "기능별 안내")],
    },
    "commands": {
        "title": "명령어와 방송 알림", "path": "/guide/commands", "template": "guide_commands.html",
        "description": "출석, 커스텀 명령어, 인사말부터 디스코드 방송 알림까지 채팅에서 관리하는 방법입니다.",
        "toc": [("basic", "기본 명령어"), ("admin", "관리자 명령어"), ("rules", "공통 규칙"),
                ("commands", "명령어 관리"), ("greetings", "인사말 관리"), ("settings", "봇 설정"),
                ("notice", "채팅 공지"), ("discord", "디스코드 알림")],
    },
    "overlays": {
        "title": "채팅·타이머 오버레이", "path": "/guide/overlays", "template": "guide_overlays.html",
        "description": "OBS에 채팅창과 타이머를 연결하고, 방송에 맞게 디자인을 조정하세요.",
        "toc": [("connect", "OBS 연결"), ("chat", "채팅 오버레이"), ("timer", "타이머 오버레이")],
    },
    "drawing-donation": {
        "title": "그림 도네이션", "path": "/guide/drawing-donation", "template": "guide_drawing_donation.html",
        "description": "시청자가 그린 과정이 방송에서 재생됩니다. 스트리머 설정과 시청자 참여 방법을 안내합니다.",
        "toc": [("streamer", "스트리머 설정"), ("options", "재생 설정"), ("viewer", "시청자 참여"),
                ("playback", "후원과 재생"), ("help", "그림이 나오지 않을 때")],
    },
}


def render_guide(request: Request, key: str):
    page = GUIDE_PAGES[key]
    return templates.TemplateResponse(request=request, name=page["template"], context={
        "request": request, "public_site_url": PUBLIC_SITE_URL, "page": page,
        "guide_pages": list(GUIDE_PAGES.values()),
    })


@guide_router.get("/guide", response_class=HTMLResponse)
async def get_guide(request: Request):
    return render_guide(request, "")


@guide_router.get("/guide/{page_key}", response_class=HTMLResponse)
async def get_guide_page(page_key: str, request: Request):
    if page_key not in GUIDE_PAGES:
        raise HTTPException(404, "가이드를 찾을 수 없습니다.")
    return render_guide(request, page_key)


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
    entries = "\n".join(
        f"  <url><loc>{escape(PUBLIC_SITE_URL + page['path'])}</loc><changefreq>weekly</changefreq></url>"
        for page in GUIDE_PAGES.values()
    )
    content = f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{entries}\n</urlset>\n'
    return Response(content=content, media_type="application/xml")
