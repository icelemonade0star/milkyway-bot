import asyncio
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit
from xml.etree import ElementTree

import httpx
import pytest
from fastapi import FastAPI

from app.features.guide.router import guide_router

ROOT = Path(__file__).resolve().parents[1]
PATHS = ["/guide", "/guide/commands", "/guide/overlays", "/guide/drawing-donation"]


class Links(HTMLParser):
    def __init__(self, text: str):
        super().__init__()
        self.ids: set[str] = set()
        self.hrefs: list[str] = []
        self.canonical: str | None = None
        self.feed(text)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        attributes = dict(attrs)
        element_id = attributes.get("id")
        if element_id is not None:
            self.ids.add(element_id)
        if tag == "a":
            self.hrefs.append(attributes.get("href") or "")
        if tag == "link" and attributes.get("rel") == "canonical":
            self.canonical = attributes.get("href")


def app():
    instance = FastAPI()
    instance.include_router(guide_router)
    return instance


@pytest.mark.parametrize("path", PATHS)
def test_guide_pages_are_public_with_working_navigation_and_page_metadata(path):
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app()), base_url="http://test") as client:
            response = await client.get(path)
        assert response.status_code == 200
        links = Links(response.text)
        assert set(PATHS) <= set(links.hrefs)
        assert all(href[1:] in links.ids for href in links.hrefs if href.startswith("#"))
        assert links.canonical is not None, "canonical 링크가 없습니다."
        assert links.canonical.endswith(path)
        match = re.search(r'<script type="application/ld\+json">(.*?)</script>', response.text, re.S)
        assert match is not None, "JSON-LD 메타데이터가 없습니다."
        structured = json.loads(match.group(1))
        assert structured["url"] == links.canonical
        assert structured["inLanguage"] == "ko"
    asyncio.run(run())


def test_home_is_short_and_details_live_on_feature_pages():
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app()), base_url="http://test") as client:
            home = (await client.get("/guide")).text
            commands = (await client.get("/guide/commands")).text
            overlays = (await client.get("/guide/overlays")).text
            drawing = (await client.get("/guide/drawing-donation")).text
        assert "!명령어등록" not in home and "!알림설정" not in home
        for command in ["!출석", "!명령어등록", "!인사등록", "!공지", "!알림설정", "!알림삭제"]:
            assert command in commands
        assert "!타이머 재생" in overlays and ".chat-frame" in overlays
        assert drawing.index('id="streamer"') < drawing.index('id="viewer"')
        assert "후원할 때마다 다시 재생" in drawing
        assert "/auth/dashboard/drawing" in drawing
    asyncio.run(run())


def test_sitemap_lists_all_pages_and_unknown_guide_returns_404():
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app()), base_url="http://test") as client:
            response = await client.get("/sitemap.xml")
            entries = ElementTree.fromstring(response.text).findall("{*}url/{*}loc")
            sitemap_paths = set()
            for entry in entries:
                assert entry.text is not None, "사이트맵 URL이 비어 있습니다."
                sitemap_paths.add(urlsplit(entry.text).path)
            assert sitemap_paths == set(PATHS)
            assert (await client.get("/guide/missing")).status_code == 404
            assert (await client.get("/guide/guide_base.html")).status_code == 404
            robots = (await client.get("/robots.txt")).text
            assert "Allow: /guide" in robots and "Disallow: /auth/" in robots
    asyncio.run(run())


@pytest.mark.parametrize("width", [375, 1280])
def test_browser_navigation_and_layout(width, tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    async def pages():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app()), base_url="http://test") as client:
            return {path: (await client.get(path)).text for path in PATHS}
    html = asyncio.run(pages())
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": 900})
        def serve(route):
            path = urlsplit(route.request.url).path
            if path.startswith("/static/"):
                route.fulfill(path=str(ROOT / "app" / path.lstrip("/")))
            elif path in html:
                route.fulfill(body=html[path], content_type="text/html")
            else:
                route.abort()
        page.route("**/*", serve)
        page.goto("http://localhost/guide")
        for path in PATHS:
            if width == 375:
                page.locator(".guide-mobile-nav summary").click()
                page.locator(f'.guide-mobile-nav a[href="{path}"]').click()
            else:
                page.locator(f'.guide-sidebar a[href="{path}"]').click()
            page.wait_for_url("http://localhost" + path)
            assert page.locator("h1").count() == 1
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            nav = page.locator(".guide-mobile-nav" if width == 375 else ".guide-sidebar")
            assert nav.locator('a[aria-current="page"]').get_attribute("href") == path
            filename = path.rsplit("/", 1)[-1]
            page.screenshot(path=str(tmp_path / f"{filename}-{width}.png"), full_page=True)
        browser.close()
