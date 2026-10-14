from pathlib import Path
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone

import pytest
from jinja2 import Environment, FileSystemLoader

from app.features.drawing_donation.schemas import DrawingDonationOptions, DrawingSaveRequest, Stroke

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Page, Route, sync_playwright
ROOT = Path(__file__).resolve().parents[1]
templates = Environment(loader=FileSystemLoader(ROOT / "app/templates"), autoescape=True)


def serve_assets(route: Route):
    relative = route.request.url.split("/static/", 1)[1].split("?", 1)[0]
    route.fulfill(path=str(ROOT / "app/static" / relative))


def choose_background(page: Page, mode: str) -> None:
    page.locator("#drawingBackgroundSettings").evaluate("element => element.open = true")
    page.locator(f'button[data-background-mode="{mode}"]').click()


def open_ux_editor(page: Page, saved: list, channel: str = "channel", options=None):
    html = templates.get_template("drawing.html").render(
        channel=SimpleNamespace(channel_name="테스트 스트리머", platform_channel_id=channel),
        options=options or DrawingDonationOptions(enabled=True))
    page.route("**/static/**", serve_assets)
    def editor(route: Route):
        if route.request.method == "GET":
            route.fulfill(body=html, content_type="text/html")
        else:
            saved.append(DrawingSaveRequest.model_validate(route.request.post_data_json))
            route.fulfill(json={"hashtag": "#mw-" + "a" * 24})
    page.route(f"**/drawing/chzzk/{channel}", editor)
    page.goto(f"http://localhost/drawing/chzzk/{channel}")
    page.wait_for_function("!document.getElementById('penWidth').disabled || !document.getElementById('drawingDraftPrompt').hidden")


def read_browser_draft(page: Page, key: str = "/drawing/chzzk/channel"):
    return page.evaluate("""key => new Promise((resolve, reject) => {
        const request = indexedDB.open('milkyway-drawing', 1);
        request.onsuccess = () => {
            const db = request.result, transaction = db.transaction('drafts', 'readonly');
            const read = transaction.objectStore('drafts').get(key);
            transaction.oncomplete = () => { db.close(); resolve(read.result ?? null); };
            transaction.onerror = () => reject(transaction.error);
        };
        request.onerror = () => reject(request.error);
    })""", key)


@pytest.mark.parametrize("width", [390, 1280])
def test_brush_cursor_active_controls_focus_zoom_pan_and_original_saved_coordinates(width, tmp_path):
    saved, errors = [], []
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": 1000}, has_touch=True)
        page.on("pageerror", lambda error: errors.append(str(error)))
        open_ux_editor(page, saved)
        canvas, viewport = page.locator("#drawingCanvas"), page.locator("#drawingViewport")
        assert not page.locator("#drawingBackgroundSettings").evaluate("e => e.open")
        assert page.locator("#penSizeControl").is_visible() and page.locator("#eraserSizeControl").is_hidden()
        page.locator("#penWidth").fill("24")
        canvas.scroll_into_view_if_needed()
        bounds = canvas.bounding_box()
        assert bounds is not None
        page.mouse.move(bounds["x"] + bounds["width"] / 2, bounds["y"] + bounds["height"] / 2)
        cursor = page.locator("#drawingBrushCursor")
        assert cursor.is_visible()
        assert cursor.evaluate("e => parseFloat(e.style.width)") == pytest.approx(24 * bounds["width"] / 800)
        page.locator('[data-tool="eraser"]').click()
        assert page.locator("#penSizeControl").is_hidden() and page.locator("#eraserSizeControl").is_visible()
        page.locator("#eraserWidth").fill("40")
        page.locator('[data-tool="fill"]').click()
        assert page.locator("#penSizeControl").is_hidden() and page.locator("#eraserSizeControl").is_hidden()
        assert page.locator("#brushPreview").is_hidden() and cursor.is_hidden()
        page.locator('[data-tool="pen"]').click()
        assert page.locator("#penWidth").input_value() == "24"
        canvas.click(position={"x": bounds["width"] / 2, "y": bounds["height"] / 2})
        original = canvas.evaluate("c => c.toDataURL()")
        page.locator("#focusDrawing").click()
        page.wait_for_function("document.body.classList.contains('drawing-focus')")
        page.wait_for_function("document.getElementById('drawingViewport').clientHeight > 140")
        page.locator("#zoomInDrawing").click()
        assert page.locator("#drawingZoom").text_content() == "150%"
        assert canvas.evaluate("c => [c.width, c.height]") == [800, 600]
        assert canvas.evaluate("c => c.toDataURL()") == original
        page.locator("#panDrawing").click()
        assert page.locator("#panDrawing").get_attribute("aria-pressed") == "true"
        view_bounds = viewport.bounding_box()
        assert view_bounds is not None
        before = viewport.evaluate("e => [e.scrollLeft, e.scrollTop]")
        x, y = view_bounds["x"] + view_bounds["width"] / 2, view_bounds["y"] + view_bounds["height"] / 2
        page.mouse.move(x, y)
        page.mouse.down(); page.mouse.move(x - 35, y - 35, steps=5); page.mouse.up()
        after = viewport.evaluate("e => [e.scrollLeft, e.scrollTop]")
        assert after != before
        assert cursor.is_hidden() and canvas.evaluate("c => c.toDataURL()") == original
        # 터치 이동도 선을 추가하지 않고 같은 화면 이동을 사용한다.
        cdp = page.context.new_cdp_session(page)
        cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": x, "y": y}]})
        cdp.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [{"x": x + 25, "y": y + 25}]})
        cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
        assert canvas.evaluate("c => c.toDataURL()") == original
        page.locator('[data-tool="pen"]').click()
        assert page.locator("#panDrawing").get_attribute("aria-pressed") == "false"
        page.mouse.move(x, y)
        assert cursor.is_visible()
        zoomed = canvas.bounding_box()
        assert zoomed is not None
        expected = ((x - zoomed["x"]) * 800 / zoomed["width"], (y - zoomed["y"]) * 600 / zoomed["height"])
        page.mouse.down()
        assert page.locator("#zoomInDrawing").is_disabled()
        page.mouse.up()
        page.screenshot(path=str(tmp_path / f"drawing-focus-{width}.png"), full_page=True)
        page.keyboard.press("Escape")
        assert not page.evaluate("document.body.classList.contains('drawing-focus')")
        page.locator("#fitDrawing").click()
        assert page.locator("#drawingZoom").text_content() == "100%"
        page.locator("#saveDrawing").click()
        page.locator("#drawingResult").wait_for(state="visible")
        assert len(saved) == 1 and len(saved[0].recording.actions) == 2
        point = saved[0].recording.actions[1].points[0]
        assert (point.x, point.y) == pytest.approx(expected, abs=1)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert not errors
        browser.close()


def test_draft_restores_pixels_tools_background_save_key_and_undo_then_clears_after_save():
    saved, errors = [], []
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        open_ux_editor(page, saved)
        canvas = page.locator("#drawingCanvas")
        page.locator("#penWidth").fill("18")
        page.locator('[data-color="#f6a21a"]').click()
        choose_background(page, "transparent")
        canvas.click(position={"x": 80, "y": 80})
        first = canvas.evaluate("c => c.toDataURL()")
        canvas.click(position={"x": 150, "y": 150})
        picture = canvas.evaluate("c => c.toDataURL()")
        page.wait_for_function("document.getElementById('drawingDraftStatus').textContent.includes('임시 저장했어요')")
        draft = read_browser_draft(page)
        assert draft is not None
        page.reload()
        page.locator("#drawingDraftPrompt").wait_for(state="visible")
        assert page.locator("#saveDrawing").is_disabled()
        page.locator("#restoreDrawingDraft").click()
        assert canvas.evaluate("c => c.toDataURL()") == picture
        assert page.locator("#penWidth").input_value() == "18"
        assert page.locator("#penColor").input_value() == "#f6a21a"
        assert page.locator("#canvasBackgroundMode").input_value() == "transparent"
        page.locator("#undoDrawing").click()
        assert canvas.evaluate("c => c.toDataURL()") == first
        page.locator("#redoDrawing").click()
        assert canvas.evaluate("c => c.toDataURL()") == picture
        page.wait_for_function("document.getElementById('drawingDraftStatus').textContent.includes('임시 저장했어요')")
        updated = read_browser_draft(page)
        assert updated is not None
        page.locator("#saveDrawing").click()
        page.locator("#drawingResult").wait_for(state="visible")
        assert saved[0].save_key == DrawingSaveRequest.model_validate({
            "save_key": updated["saveKey"], "recording": updated["recording"], "final_png": picture}).save_key
        assert saved[0].final_png == picture and read_browser_draft(page) is None
        page.reload()
        page.wait_for_function("!document.getElementById('penWidth').disabled")
        assert page.locator("#drawingDraftPrompt").is_hidden() and page.locator("#saveDrawing").is_disabled()
        assert not errors
        browser.close()


@pytest.mark.parametrize("broken", [False, True])
def test_draft_is_channel_scoped_and_incompatible_or_corrupt_draft_can_be_discarded(broken):
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page()
        open_ux_editor(page, [])
        page.locator("#drawingCanvas").click(position={"x": 80, "y": 80})
        page.wait_for_function("document.getElementById('drawingDraftStatus').textContent.includes('임시 저장했어요')")
        original = read_browser_draft(page)
        assert original is not None
        open_ux_editor(page, [], "other")
        assert page.locator("#drawingDraftPrompt").is_hidden()
        assert read_browser_draft(page) == original
        if broken:
            page.evaluate("""() => new Promise(resolve => {
                const request = indexedDB.open('milkyway-drawing', 1);
                request.onsuccess = () => {
                    const db = request.result, transaction = db.transaction('drafts', 'readwrite');
                    transaction.objectStore('drafts').put({version: 1, recording: null}, '/drawing/chzzk/channel');
                    transaction.oncomplete = () => { db.close(); resolve(); };
                };
            })""")
        open_ux_editor(page, [], options=DrawingDonationOptions(enabled=True, canvas_width=1280, canvas_height=720))
        assert page.locator("#drawingDraftPrompt").is_visible()
        assert page.locator("#restoreDrawingDraft").is_disabled()
        page.locator("#discardDrawingDraft").click()
        page.wait_for_function("!document.getElementById('penWidth').disabled")
        assert page.locator("#drawingDraftPrompt").is_hidden()
        assert read_browser_draft(page) is None
        browser.close()


@pytest.mark.parametrize("expired", [False, True])
def test_restored_draft_retries_original_save_key_and_can_recover_from_expired_server_save(expired):
    saved = []
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page()
        open_ux_editor(page, saved)
        canvas = page.locator("#drawingCanvas")
        canvas.click(position={"x": 80, "y": 80})
        picture = canvas.evaluate("c => c.toDataURL()")
        page.wait_for_function("document.getElementById('drawingDraftStatus').textContent.includes('임시 저장했어요')")
        original = read_browser_draft(page)
        assert original is not None
        def editor(route: Route):
            if route.request.method == "GET":
                route.fallback()
                return
            saved.append(DrawingSaveRequest.model_validate(route.request.post_data_json))
            if expired and len(saved) == 1:
                route.fulfill(status=410, json={"error": "그림 사용 시간이 지났습니다."})
            else:
                route.fulfill(json={"hashtag": "#mw-" + "a" * 24})
        page.route("**/drawing/chzzk/channel", editor)
        page.reload()
        page.locator("#restoreDrawingDraft").click()
        page.locator("#saveDrawing").click()
        if expired:
            page.wait_for_function("document.getElementById('drawingStatus').textContent.includes('이전 저장의 유효기간')")
            assert canvas.evaluate("c => c.toDataURL()") == picture
            page.locator("#saveDrawing").click()
        page.locator("#drawingResult").wait_for(state="visible")
        assert str(saved[0].save_key) == original["saveKey"]
        assert saved[-1].final_png == picture
        if expired:
            assert len(saved) == 2 and saved[-1].save_key != saved[0].save_key
        assert read_browser_draft(page) is None
        browser.close()


def test_unavailable_draft_storage_does_not_block_drawing_or_server_save():
    saved, errors = [], []
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.add_init_script("Object.defineProperty(window, 'indexedDB', {get() { throw new Error('disabled'); }});")
        open_ux_editor(page, saved)
        assert "임시 저장을 하지 못했어요" in page.locator("#drawingDraftStatus").inner_text()
        page.locator("#drawingCanvas").click(position={"x": 80, "y": 80})
        page.locator("#saveDrawing").click()
        page.locator("#drawingResult").wait_for(state="visible")
        assert len(saved) == 1 and not errors
        browser.close()


@pytest.mark.parametrize("size", [(800, 600), (1280, 720)])
def test_draw_save_and_replay_in_browser(tmp_path, size):
    options = DrawingDonationOptions(enabled=True, replay_seconds=3, hold_seconds=2,
                                     canvas_width=size[0], canvas_height=size[1])
    html = templates.get_template("drawing.html").render(
        channel=SimpleNamespace(channel_name="테스트 스트리머", platform_channel_id="channel"), options=options)
    saved = []
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 1000})
        page.route("**/static/**", serve_assets)
        def drawing_route(route):
            if route.request.method == "GET":
                route.fulfill(body=html, content_type="text/html")
            else:
                saved.append(DrawingSaveRequest.model_validate(route.request.post_data_json))
                route.fulfill(json={"hashtag": "#mw-" + "a" * 24})
        page.route("**/drawing/chzzk/channel", drawing_route)
        page.goto("http://localhost/drawing/chzzk/channel")
        canvas = page.locator("#drawingCanvas")
        box = canvas.bounding_box()
        assert box
        def draw(start, end):
            scale_x, scale_y = box["width"] / options.canvas_width, box["height"] / options.canvas_height
            page.mouse.move(box["x"] + start[0] * scale_x, box["y"] + start[1] * scale_y)
            page.mouse.down()
            page.mouse.move(box["x"] + end[0] * scale_x, box["y"] + end[1] * scale_y, steps=12)
            page.mouse.up()
        page.locator("#penWidth").fill("20")
        draw((80, 80), (360, 80))
        assert canvas.evaluate("c => Array.from(c.getContext('2d').getImageData(200,80,1,1).data)")[:3] == [37, 69, 60]
        page.locator('[data-tool="eraser"]').click()
        assert page.locator("#eraserWidth").input_value() == "20"
        page.locator("#eraserWidth").fill("32")
        assert page.locator("#brushPreviewDot").evaluate("e => e.style.width") == "32px"
        draw((180, 80), (260, 80))
        assert canvas.evaluate("c => Array.from(c.getContext('2d').getImageData(200,80,1,1).data)")[3] == 0
        page.locator("#undoDrawing").click()
        assert canvas.evaluate("c => Array.from(c.getContext('2d').getImageData(200,80,1,1).data)")[:3] == [37, 69, 60]
        page.locator("#clearDrawing").click()
        page.locator("#confirmClearDrawing").click()
        page.locator('[data-tool="pen"]').click()
        assert page.locator("#penWidth").input_value() == "20"
        assert page.locator("#brushPreviewDot").evaluate("e => e.style.width") == "20px"
        draw((80, 140), (240, 260))
        page.locator("#saveDrawing").click()
        page.wait_for_function("document.getElementById('drawingTag').value.startsWith('#mw-')")
        assert len(saved) == 1
        payload = saved[0]
        assert (payload.recording.width, payload.recording.height) == size
        assert [action.type for action in payload.recording.actions] == ["stroke"]
        page.screenshot(path=str(tmp_path / "drawing-editor.png"), full_page=True)

        overlay = browser.new_page(viewport={"width": 700, "height": 600})
        overlay.route("**/static/**", serve_assets)
        overlay_html = templates.get_template("drawing_overlay.html").render(
            options=options.model_dump(), poll_path="/drawing/overlay/test/next", preview=False)
        overlay.route("**/drawing/overlay/test", lambda route: route.fulfill(body=overlay_html, content_type="text/html"))
        job = {"id": "1", "nickname": "<img src=x>", "amount": 1000, "recording": payload.recording.model_dump(),
               "elapsed_ms": 0, "options": options.model_dump()}
        overlay.route("**/drawing/overlay/test/next*", lambda route: route.fulfill(json={
            "playback": None if "current=" in route.request.url else job, "current_id": "1", "options": options.model_dump()}))
        overlay.goto("http://localhost/drawing/overlay/test")
        overlay.wait_for_function("!document.getElementById('drawingOverlay').hidden")
        assert overlay.locator("#drawingDonor img").count() == 0
        assert "<img src=x>" in overlay.locator("#drawingDonor").inner_text()
        overlay.wait_for_function("png => document.getElementById('replayCanvas').toDataURL('image/png') === png",
                                  arg=payload.final_png, timeout=6000)
        overlay.screenshot(path=str(tmp_path / "drawing-overlay.png"))
        browser.close()


def test_editor_records_independent_pen_and_eraser_widths():
    html = templates.get_template("drawing.html").render(
        channel=SimpleNamespace(channel_name="테스트 스트리머", platform_channel_id="channel"),
        options=DrawingDonationOptions(enabled=True))
    saved = []
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 1100})
        page.route("**/static/**", serve_assets)
        def editor(route: Route):
            if route.request.method == "GET":
                route.fulfill(body=html, content_type="text/html")
            else:
                saved.append(DrawingSaveRequest.model_validate(route.request.post_data_json))
                route.fulfill(json={"hashtag": "#mw-" + "a" * 24})
        page.route("**/drawing/chzzk/channel", editor)
        page.goto("http://localhost/drawing/chzzk/channel")
        canvas = page.locator("#drawingCanvas")
        page.locator("#penWidth").fill("12")
        canvas.click(position={"x": 50, "y": 50})
        page.locator('[data-tool="eraser"]').click()
        page.locator("#eraserWidth").fill("40")
        canvas.click(position={"x": 50, "y": 50})
        page.locator('[data-tool="pen"]').click()
        assert page.locator("#brushPreviewDot").evaluate("e => e.style.width") == "12px"
        canvas.click(position={"x": 80, "y": 80})
        page.locator('[data-tool="eraser"]').click()
        assert page.locator("#eraserWidth").input_value() == "40"
        canvas.click(position={"x": 80, "y": 80})
        page.locator("#saveDrawing").click()
        page.wait_for_function("document.getElementById('drawingTag').value.startsWith('#mw-')")
        assert [(action.tool, action.width) for action in saved[0].recording.actions] == [
            ("pen", 12), ("eraser", 40), ("pen", 12), ("eraser", 40)]
        assert page.locator("#penWidth").is_disabled() and page.locator("#eraserWidth").is_disabled()
        browser.close()


@pytest.mark.parametrize("width", [390, 1280])
def test_dashboard_hashtag_replay_posts_to_broadcast_queue_and_recovers_from_errors(width):
    html = templates.get_template("dashboard_drawing_playback.html").render(
        channel=SimpleNamespace(channel_name="테스트 스트리머"), options=DrawingDonationOptions(enabled=True),
        drawing_url="/drawing/chzzk/channel", overlay_url="/drawing/overlay/test", preview_path="/drawing/overlay/test?preview=1")
    requests, errors = [], []
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": 1100})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route("**/static/**", serve_assets)
        page.route("**/auth/dashboard/drawing/playback", lambda route: route.fulfill(body=html, content_type="text/html"))
        page.route("**/drawing/overlay/test?preview=1", lambda route: route.fulfill(body="<html></html>", content_type="text/html"))
        page.route("**/auth/dashboard/drawing/history", lambda route: route.fulfill(json={
            "items": [], "next_cursor": None, "enabled": True, "server_now": datetime.now(timezone.utc).isoformat()}))
        def replay(route: Route):
            assert route.request.method == "POST"
            requests.append(route.request.post_data_json)
            if len(requests) == 1:
                route.fulfill(status=410, json={"detail": "그림 사용 시간이 지났습니다."})
            elif len(requests) == 2:
                route.fulfill(json={"id": "1", "status": "queued", "already_queued": False})
            elif len(requests) == 3:
                route.fulfill(json={"id": "1", "status": "playing", "already_queued": True})
            else:
                route.fulfill(status=503, body="unavailable", content_type="text/html")
        page.route("**/auth/dashboard/drawing/replay", replay)
        page.goto("http://localhost/auth/dashboard/drawing/playback")
        field = page.get_by_label("그림 해시태그", exact=True)
        button = page.get_by_role("button", name="방송에서 재생", exact=True)
        field.fill("  #mw-" + "a" * 24 + "  ")
        field.press("Enter")
        page.wait_for_function("document.getElementById('hashtagReplayStatus').textContent.includes('사용 시간이')")
        assert button.is_enabled()
        button.click()
        page.wait_for_function("document.getElementById('hashtagReplayStatus').textContent.includes('추가했어요')")
        button.click()
        page.wait_for_function("document.getElementById('hashtagReplayStatus').textContent.includes('이미 방송')")
        button.click()
        page.wait_for_function("document.getElementById('hashtagReplayStatus').textContent.includes('실패했어요')")
        assert button.is_enabled()
        assert requests == [{"hashtag": "#mw-" + "a" * 24}] * 4
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        assert not errors
        browser.close()


@pytest.mark.parametrize("width", [390, 1280])
def test_dashboard_queue_donors_sources_thumbnails_cancel_and_live_updates(width, tmp_path):
    html = templates.get_template("dashboard_drawing_playback.html").render(
        channel=SimpleNamespace(channel_name="테스트 스트리머"), options=DrawingDonationOptions(enabled=True),
        drawing_url="/drawing/chzzk/channel", overlay_url="/drawing/overlay/test", preview_path="/drawing/overlay/test?preview=1")
    now = datetime.now(timezone.utc)
    malicious = '<img src=x onerror="alert(1)">'
    state = {"items": [
        {"id": "1", "drawing_id": "shared", "status": "playing", "source": "donation", "nickname": malicious, "amount": 5000},
        {"id": "2", "drawing_id": "shared", "status": "queued", "source": "hashtag", "nickname": "스트리머 수동 재생", "amount": 0},
        {"id": "3", "drawing_id": "other", "status": "queued", "source": "replay", "nickname": "원래 후원자", "amount": 2500},
    ]}
    recording = {"width": 400, "height": 300, "actions": [{"type": "stroke", "tool": "pen", "color": "#246544",
        "width": 20, "points": [{"x": 40, "y": 40, "t": 0}, {"x": 120, "y": 40, "t": 1000}]}]}
    requests, previews, cancellations, errors, queue_reads = [], [], [], [], []
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": 1100})
        page.clock.install(time=now)
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("request", lambda request: requests.append(request.url))
        page.route("**/static/**", serve_assets)
        page.route("**/auth/dashboard/drawing/playback", lambda route: route.fulfill(body=html, content_type="text/html"))
        page.route("**/drawing/overlay/test?preview=1", lambda route: route.fulfill(body="<html></html>", content_type="text/html"))
        page.route("**/auth/dashboard/drawing/history*", lambda route: route.fulfill(json={
            "items": [], "next_cursor": None, "enabled": True, "server_now": now.isoformat()}))
        def queue(route: Route):
            queue_reads.append(route.request.url)
            rows = [{**item, "position": index + 1, "hashtag": "#mw-" + "a" * 24,
                "expires_at": (now + timedelta(hours=1)).isoformat()} for index, item in enumerate(state["items"])]
            playing = sum(item["status"] == "playing" for item in rows)
            route.fulfill(json={"items": rows, "offset": 0, "limit": 20, "total_count": len(rows),
                "playing_count": playing, "queued_count": len(rows) - playing, "enabled": True, "server_now": now.isoformat()})
        page.route("**/auth/dashboard/drawing/queue*", queue)
        def cancel(route: Route):
            assert route.request.method == "DELETE"
            cancellations.append(route.request.url)
            if len(cancellations) == 1:
                route.fulfill(status=503, json={"error": "취소 요청에 실패했어요. 다시 시도해주세요."})
            else:
                state["items"] = state["items"][1:]
                route.fulfill(json={"id": "1", "status": "cancelled", "was_playing": True})
        page.route("**/auth/dashboard/drawing/queue/*", cancel)
        def preview(route: Route):
            previews.append(route.request.url)
            route.fulfill(json={"recording": recording})
        page.route("**/auth/dashboard/drawing/queue/*/recording", preview)
        page.goto("http://localhost/auth/dashboard/drawing/playback")
        panel = page.locator(".drawing-queue")
        panel.scroll_into_view_if_needed()
        page.wait_for_function("document.querySelectorAll('.drawing-queue-item').length === 3")
        cards = page.locator(".drawing-queue-item")
        assert "전체 3개 · 재생 중 1개 · 대기 2개" in page.locator("#drawingQueueSummary").inner_text()
        assert "1번" in cards.nth(0).inner_text() and "현재 재생 중" in cards.nth(0).inner_text()
        assert malicious in cards.nth(0).inner_text() and "5,000원" in cards.nth(0).inner_text()
        assert cards.nth(0).locator(".drawing-history-details img").count() == 0
        assert "해시태그 수동 재생" in cards.nth(1).inner_text() and "0원" not in cards.nth(1).inner_text()
        assert "후원 그림 다시 재생" in cards.nth(2).inner_text() and "원래 후원자" in cards.nth(2).inner_text()
        cards.nth(2).scroll_into_view_if_needed()
        page.wait_for_function("Array.from(document.querySelectorAll('.drawing-queue-item img')).every(image => image.src.startsWith('data:image/png'))")
        assert len(previews) == 2
        cards.nth(0).get_by_role("button", name="재생 중단").click()
        page.locator("#confirmCancelDrawingQueue").click()
        page.wait_for_function("document.getElementById('drawingQueueStatus').textContent.includes('취소 요청에 실패')")
        assert cards.nth(0).get_by_role("button", name="재생 중단").is_enabled()
        cards.nth(0).get_by_role("button", name="재생 중단").click()
        page.locator("#confirmCancelDrawingQueue").click()
        page.wait_for_function("document.querySelectorAll('.drawing-queue-item').length === 2")
        page.wait_for_function("document.getElementById('drawingQueueSummary').textContent.includes('전체 2개')")
        assert "1번" in cards.nth(0).inner_text() and "수동 재생" in cards.nth(0).inner_text()
        assert len(cancellations) == 2 and not any("/next" in url for url in requests)
        state["items"][0]["status"] = "playing"
        page.clock.fast_forward(3100)
        page.wait_for_function("document.querySelector('.drawing-queue-item').classList.contains('is-playing')")
        page.screenshot(path=str(tmp_path / f"drawing-queue-{width}.png"), full_page=True)
        page.evaluate("Object.defineProperty(document, 'visibilityState', {value: 'hidden', configurable: true})")
        reads = len(queue_reads)
        page.clock.fast_forward(6100)
        assert len(queue_reads) == reads
        state["items"] = []
        page.evaluate("""() => {
            Object.defineProperty(document, 'visibilityState', {value: 'visible', configurable: true});
            document.dispatchEvent(new Event('visibilitychange'));
        }""")
        page.locator("#drawingQueueEmpty").wait_for(state="visible")
        assert cards.count() == 0 and not errors
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        browser.close()


def test_dashboard_queue_paging_disabled_cancel_and_errors_recover():
    html = templates.get_template("dashboard_drawing_playback.html").render(
        channel=SimpleNamespace(channel_name="테스트"), options=DrawingDonationOptions(enabled=False),
        drawing_url="/drawing/chzzk/channel", overlay_url="/drawing/overlay/test", preview_path="/drawing/overlay/test?preview=1")
    identities = [str(value) for value in range(1, 22)] + ["9007199254740993"]
    calls = 0
    offsets, deleted, errors = [], [], []
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page()
        page.clock.install()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route("**/static/**", serve_assets)
        page.route("**/auth/dashboard/drawing/playback", lambda route: route.fulfill(body=html, content_type="text/html"))
        page.route("**/drawing/overlay/test?preview=1", lambda route: route.fulfill(body="<html></html>", content_type="text/html"))
        page.route("**/auth/dashboard/drawing/history*", lambda route: route.fulfill(json={
            "items": [], "next_cursor": None, "enabled": False, "server_now": datetime.now(timezone.utc).isoformat()}))
        def queue(route: Route):
            nonlocal calls
            calls += 1
            if calls == 1:
                route.fulfill(status=503, body="unavailable", content_type="text/html")
                return
            offset = 20 if "offset=20" in route.request.url else 0
            offsets.append(offset)
            rows = [{"id": identity, "drawing_id": "shared", "position": offset + index + 1, "status": "queued",
                "source": "donation", "nickname": "익명", "amount": 1000, "hashtag": "#mw-" + "a" * 24}
                for index, identity in enumerate(identities[offset:offset + 20])]
            route.fulfill(json={"items": rows, "total_count": len(identities), "queued_count": len(identities),
                "playing_count": 0, "enabled": False})
        page.route("**/auth/dashboard/drawing/queue*", queue)
        def cancel(route: Route):
            assert route.request.method == "DELETE"
            identity = route.request.url.rsplit("/", 1)[1]
            deleted.append(identity)
            identities.remove(identity)
            route.fulfill(json={"id": identity, "status": "cancelled", "was_playing": False})
        page.route("**/auth/dashboard/drawing/queue/*", cancel)
        page.route("**/auth/dashboard/drawing/queue/*/recording", lambda route: route.fulfill(status=503, body="unavailable"))
        page.goto("http://localhost/auth/dashboard/drawing/playback")
        page.wait_for_function("document.getElementById('drawingQueueStatus').textContent.includes('대기열 요청')")
        page.locator("#refreshDrawingQueue").click()
        page.wait_for_function("document.querySelectorAll('.drawing-queue-item').length === 20")
        assert page.locator("#drawingQueueStatus").inner_text() == ""
        assert "꺼져 있어요" in page.locator("#drawingQueueSummary").inner_text()
        assert page.locator("#previousDrawingQueue").is_disabled() and page.locator("#nextDrawingQueue").is_enabled()
        page.locator("#nextDrawingQueue").click()
        page.wait_for_function("document.querySelectorAll('.drawing-queue-item').length === 2")
        assert page.locator("#drawingQueuePage").inner_text() == "2 / 2 페이지"
        cards = page.locator(".drawing-queue-item")
        assert "21번" in cards.nth(0).inner_text() and "22번" in cards.nth(1).inner_text()
        assert cards.nth(1).get_by_role("button", name="재생 취소").is_enabled()
        cards.nth(1).get_by_role("button", name="재생 취소").click()
        page.locator("#confirmCancelDrawingQueue").click()
        page.wait_for_function("document.querySelectorAll('.drawing-queue-item').length === 1")
        cards.nth(0).get_by_role("button", name="재생 취소").click()
        page.locator("#confirmCancelDrawingQueue").click()
        page.wait_for_function("document.querySelectorAll('.drawing-queue-item').length === 20")
        assert deleted == ["9007199254740993", "21"]
        assert page.locator("#drawingQueuePage").inner_text() == "1 / 1 페이지"
        assert page.locator("#previousDrawingQueue").is_disabled() and page.locator("#nextDrawingQueue").is_disabled()
        assert offsets[-2:] == [20, 0] and not errors
        browser.close()


def test_queue_confirmation_freezes_pending_refresh_and_cancels_only_selected_id(tmp_path):
    html = templates.get_template("dashboard_drawing_playback.html").render(
        channel=SimpleNamespace(channel_name="테스트 스트리머"), options=DrawingDonationOptions(enabled=True))
    identities = ["1", "2"]
    reads, deletes, pending, errors = [], [], [], []
    now = datetime.now(timezone.utc)
    hold = False
    def data():
        return {"items": [{"id": identity, "drawing_id": identity, "hashtag": "#mw-" + identity * 24,
            "position": index + 1, "status": "playing" if identity == "1" else "queued", "source": "donation",
            "nickname": "첫 후원자" if identity == "1" else "선택한 후원자" if identity == "2" else "다음 후원자",
            "amount": 1000, "started_at": now.isoformat(), "duration_ms": 10000}
            for index, identity in enumerate(identities)], "total_count": len(identities), "playing_count": int("1" in identities),
            "queued_count": len(identities) - int("1" in identities), "enabled": True, "server_now": now.isoformat()}
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.clock.install(time=now)
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route("**/static/**", serve_assets)
        page.route("**/auth/dashboard/drawing/playback", lambda route: route.fulfill(body=html, content_type="text/html"))
        page.route("**/auth/dashboard/drawing/history*", lambda route: route.fulfill(json={
            "items": [], "enabled": True, "server_now": now.isoformat(), "next_cursor": None}))
        def queue(route: Route):
            reads.append(route.request.url)
            if hold:
                pending.append(route)
            else:
                route.fulfill(json=data())
        page.route("**/auth/dashboard/drawing/queue*", queue)
        def cancel(route: Route):
            assert route.request.method == "DELETE"
            deletes.append(route.request.url.rsplit("/", 1)[1])
            identities[:] = ["3"]
            route.fulfill(status=404, json={"error": "이미 재생이 끝났거나 취소된 그림입니다."})
        page.route("**/auth/dashboard/drawing/queue/*", cancel)
        page.route("**/auth/dashboard/drawing/queue/*/recording", lambda route: route.fulfill(status=404, json={"error": "없음"}))
        page.goto("http://localhost/auth/dashboard/drawing/playback")
        page.wait_for_function("document.querySelectorAll('.drawing-queue-item').length === 2")
        cards = page.locator(".drawing-queue-item")
        cards.nth(0).get_by_role("button", name="재생 중단").click()
        dialog = page.locator("#cancelDrawingQueueDialog")
        assert dialog.get_by_role("heading", name="재생을 중단할까요?").is_visible()
        assert "첫 후원자" in dialog.inner_text() and "재생 이력에서도 삭제" in dialog.inner_text()
        page.keyboard.press("Escape")
        assert not deletes
        hold = True
        page.clock.fast_forward(3100)
        page.wait_for_function("document.getElementById('refreshDrawingQueue').disabled")
        button = cards.nth(1).get_by_role("button", name="재생 취소")
        button.scroll_into_view_if_needed()
        bounds = button.bounding_box()
        assert bounds is not None and pending
        page.mouse.move(bounds["x"] + bounds["width"] / 2, bounds["y"] + bounds["height"] / 2)
        page.mouse.down()
        identities[:] = ["2"]
        pending.pop().fulfill(json=data())
        page.wait_for_function("document.getElementById('refreshDrawingQueue').disabled")
        assert cards.count() == 2 and "첫 후원자" in cards.nth(0).inner_text()
        page.mouse.up()
        dialog.wait_for(state="visible")
        assert dialog.get_by_role("heading", name="이 그림의 재생을 취소할까요?").is_visible()
        assert "선택한 후원자" in dialog.inner_text() and "2번" in dialog.inner_text()
        reads_before = len(reads)
        page.clock.fast_forward(6100)
        page.evaluate("window.dispatchEvent(new Event('drawing-queue-changed'))")
        assert len(reads) == reads_before and cards.count() == 2 and not deletes
        page.screenshot(path=str(tmp_path / "queue-cancel-confirmation.png"), full_page=True)
        hold = False
        page.locator("#confirmCancelDrawingQueue").click()
        page.wait_for_function("document.getElementById('drawingQueueStatus').textContent.includes('이미 재생이 끝났거나')")
        page.wait_for_function("document.querySelectorAll('.drawing-queue-item').length === 1")
        assert deletes == ["2"] and "다음 후원자" in cards.nth(0).inner_text()
        cards.nth(0).get_by_role("button", name="재생 취소").click()
        dialog.get_by_role("button", name="돌아가기").click()
        assert deletes == ["2"] and not errors
        browser.close()


@pytest.mark.parametrize("width", [390, 1280])
def test_settings_menu_copy_feedback_unsaved_changes_and_widescreen_preview(width, tmp_path):
    options = DrawingDonationOptions(enabled=False)
    html = templates.get_template("dashboard_drawing.html").render(
        channel=SimpleNamespace(channel_name="테스트 스트리머"), options=options,
        drawing_url="http://localhost/drawing/chzzk/channel", overlay_url="http://localhost/drawing/overlay/test",
        preview_path="/drawing/overlay/test?preview=1")
    saved, errors = [], []
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": 844})
        page.clock.install()
        page.add_init_script("""Object.defineProperty(navigator, 'clipboard', {value: {
            writeText: async value => { if (window.failDrawingCopy) throw new Error('denied'); window.copiedLink = value; }
        }});""")
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route("**/static/**", serve_assets)
        def settings(route: Route):
            if route.request.method == "GET":
                route.fulfill(body=html, content_type="text/html")
            else:
                saved.append(route.request.post_data_json)
                route.fulfill(json={"status": "success", "options": saved[-1]})
        page.route("**/auth/dashboard/drawing", settings)
        page.route("**/drawing/overlay/test?preview=1", lambda route: route.fulfill(body="<html></html>", content_type="text/html"))
        page.route("**/auth/dashboard/drawing/queue*", lambda route: route.fulfill(json={"playing_count": 1, "queued_count": 2}))
        page.goto("http://localhost/auth/dashboard/drawing")
        page.wait_for_function("document.getElementById('drawingQueueNavSummary').textContent.includes('재생 중 1')")
        assert page.get_by_role("link", name="재생 관리", exact=True).get_attribute("href") == "/auth/dashboard/drawing/playback"
        assert page.locator("#drawingQueueList, #drawingHashtagReplay").count() == 0
        assert page.locator("#drawingSettingsDirty").is_hidden()
        page.locator('[name="enabled"]').check()
        assert "아직 저장되지 않았어요" in page.locator("#drawingSettingsDirty").inner_text()
        page.locator('[name="enabled"]').uncheck()
        assert page.locator("#drawingSettingsDirty").is_hidden()
        page.locator('[data-copy="drawingPageLink"]').click()
        page.wait_for_function("document.getElementById('drawingPageLinkStatus').textContent.includes('복사했어요')")
        assert page.locator("#settingsStatus").inner_text() == ""
        page.locator('[data-copy="drawingPageLink"]').click()
        page.clock.fast_forward(2100)
        assert page.locator('[data-copy="drawingPageLink"]').inner_text() == "그림 페이지 링크 복사"
        page.evaluate("window.failDrawingCopy = true")
        page.locator('[data-copy="drawingOverlayLink"]').click()
        page.wait_for_function("document.getElementById('drawingOverlayLinkStatus').textContent.includes('직접 복사')")
        assert page.locator("#settingsStatus").inner_text() == ""
        assert page.locator("#drawingOverlayLink").evaluate("e => e.selectionStart === 0 && e.selectionEnd === e.value.length")
        preview = page.locator(".drawing-preview").bounding_box()
        assert preview is not None and preview["width"] / preview["height"] == pytest.approx(16 / 9, abs=.02)
        page.locator('[name="enabled"]').check()
        page.locator('#drawingSettings [type="submit"]').click()
        page.wait_for_function("document.getElementById('settingsStatus').textContent === '설정을 저장했어요.'")
        assert saved[0]["enabled"] is True and page.locator("#drawingSettingsDirty").is_hidden()
        page.screenshot(path=str(tmp_path / f"drawing-settings-{width}.png"), full_page=True)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth") and not errors
        browser.close()


def test_playback_progress_disabled_receiving_and_single_page_navigation_are_clear(tmp_path):
    html = templates.get_template("dashboard_drawing_playback.html").render(
        channel=SimpleNamespace(channel_name="테스트 스트리머"), options=DrawingDonationOptions(enabled=False))
    now = datetime.now(timezone.utc)
    enabled = False
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.clock.install(time=now)
        page.route("**/static/**", serve_assets)
        page.route("**/auth/dashboard/drawing/playback", lambda route: route.fulfill(body=html, content_type="text/html"))
        page.route("**/auth/dashboard/drawing/history*", lambda route: route.fulfill(json={
            "items": [], "enabled": enabled, "server_now": now.isoformat(), "next_cursor": None}))
        def queue(route: Route):
            route.fulfill(json={"items": [{"id": "1", "drawing_id": "1", "hashtag": "#mw-" + "a" * 24,
                "position": 1, "status": "playing", "source": "donation", "nickname": "후원자", "amount": 1000,
                "started_at": (now - timedelta(seconds=3)).isoformat(), "duration_ms": 10000}],
                "total_count": 1, "playing_count": 1, "queued_count": 0, "enabled": enabled, "server_now": now.isoformat()})
        page.route("**/auth/dashboard/drawing/queue*", queue)
        page.route("**/auth/dashboard/drawing/queue/*/recording", lambda route: route.fulfill(status=404, json={"error": "없음"}))
        page.goto("http://localhost/auth/dashboard/drawing/playback")
        page.wait_for_function("document.querySelectorAll('.drawing-queue-item').length === 1")
        assert page.locator("#drawingQueueHeading").evaluate("e => e.getBoundingClientRect().top") < 500
        assert page.locator("#drawingQueuePages").is_hidden()
        assert page.locator("#drawingHashtagReplay button").is_disabled() and page.locator("#drawingReceivingNotice").is_visible()
        assert page.locator("#drawingSetupNotice").is_visible()
        assert page.locator("#drawingSetupNotice a").get_attribute("href") == "/auth/dashboard/drawing"
        assert page.locator(".drawing-queue-progress").is_hidden()
        assert "실제 방송" in page.locator(".broadcast-replay .broadcast-notice").inner_text()
        assert page.locator("#drawingPreview, #testDrawing").count() == 0
        enabled = True
        page.locator("#refreshDrawingQueue").click()
        page.wait_for_function("!document.querySelector('#drawingHashtagReplay button').disabled")
        assert page.locator("#drawingSetupNotice").is_hidden()
        assert page.locator(".drawing-queue-progress").evaluate("e => e.value") == pytest.approx(.3, abs=.01)
        assert "남은 시간 7초" in page.locator(".drawing-queue-remaining").inner_text()
        page.clock.fast_forward(1100)
        assert "남은 시간 6초" in page.locator(".drawing-queue-remaining").inner_text()
        assert page.locator(".cancel-drawing").evaluate("e => e.getBoundingClientRect().height") >= 44
        page.screenshot(path=str(tmp_path / "drawing-playback-progress.png"), full_page=True)
        browser.close()


def test_drawing_strokes_match_incremental_editing_and_cached_playback():
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page()
        page.add_script_tag(path=str(ROOT / "app/static/js/drawing_canvas.js"))
        result = page.evaluate((ROOT / "tests/drawing_canvas_regression.js").read_text(encoding="utf-8"))
        assert all(case["differences"] == 0 for case in result["editing"]), result["editing"]
        assert result["wrongColor"] == 0
        assert all(case["differences"] == 0 for case in result["playback"]), result["playback"]
        assert result["finalDifferences"] == 0
        assert result["repeatedReads"] == result["repeatedStrokes"] == 0
        browser.close()


def test_palette_fill_and_ctrl_z_are_editor_only():
    options = DrawingDonationOptions(enabled=True)
    html = templates.get_template("drawing.html").render(
        channel=SimpleNamespace(channel_name="테스트 스트리머", platform_channel_id="channel"), options=options)
    saved = []
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 1000})
        page.add_init_script("""window.drawingTestTimeOffset = 0;
            const realNow = performance.now.bind(performance);
            performance.now = () => realNow() + window.drawingTestTimeOffset;
        """)
        page.route("**/static/**", serve_assets)
        def drawing_route(route):
            if route.request.method == "GET":
                route.fulfill(body=html, content_type="text/html")
            else:
                saved.append(DrawingSaveRequest.model_validate(route.request.post_data_json))
                route.fulfill(json={"hashtag": "#mw-" + "b" * 24})
        page.route("**/drawing/chzzk/channel", drawing_route)
        page.goto("http://localhost/drawing/chzzk/channel")
        canvas = page.locator("#drawingCanvas")
        box = canvas.bounding_box()
        assert box
        scale_x, scale_y = box["width"] / options.canvas_width, box["height"] / options.canvas_height
        def draw(start, end):
            page.mouse.move(box["x"] + start[0] * scale_x, box["y"] + start[1] * scale_y)
            page.mouse.down()
            page.mouse.move(box["x"] + end[0] * scale_x, box["y"] + end[1] * scale_y, steps=12)
            page.mouse.up()
        page.locator('[data-color="#ef3b3f"]').click()
        assert page.locator("#penColor").input_value() == "#ef3b3f"
        draw((80, 80), (360, 80))
        assert canvas.evaluate("c => Array.from(c.getContext('2d').getImageData(200,80,1,1).data)")[3] == 255
        page.keyboard.press("Control+z")
        assert canvas.evaluate("c => Array.from(c.getContext('2d').getImageData(200,80,1,1).data)")[3] == 0
        draw((80, 80), (360, 80))
        page.evaluate("window.drawingTestTimeOffset += 600001")
        page.locator("#clearDrawing").click()
        page.locator("#confirmClearDrawing").click()
        assert canvas.evaluate("c => Array.from(c.getContext('2d').getImageData(200,80,1,1).data)")[3] == 0
        page.keyboard.press("Control+z")
        assert canvas.evaluate("c => Array.from(c.getContext('2d').getImageData(200,80,1,1).data)")[:3] == [239, 59, 63]
        draw((80, 160), (360, 160))
        assert canvas.evaluate("c => Array.from(c.getContext('2d').getImageData(200,160,1,1).data)")[3] == 255
        page.locator("#clearDrawing").click()
        page.locator("#confirmClearDrawing").click()
        page.locator('[data-color="#2f6ee5"]').click()
        page.locator('[data-tool="fill"]').click()
        page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        page.locator("#saveDrawing").click()
        page.wait_for_function("document.getElementById('drawingTag').value.startsWith('#mw-')")
        assert len(saved) == 1
        assert len(saved[0].recording.actions) == 1
        action = saved[0].recording.actions[0]
        assert isinstance(action, Stroke) and action.tool == "fill" and action.color == "#2f6ee5"
        assert action.points[0].t < 1000
        browser.close()


def test_overlay_replays_fill_with_transparent_background():
    options = DrawingDonationOptions(enabled=True, replay_seconds=3, hold_seconds=1,
                                     canvas_width=400, canvas_height=300, show_donor=False)
    html = templates.get_template("drawing_overlay.html").render(
        options=options.model_dump(), poll_path="/drawing/overlay/test/next", preview=False)
    job = {"id": "1", "nickname": "시청자", "amount": 1000, "elapsed_ms": 0, "options": options.model_dump(),
           "recording": {"width": 400, "height": 300, "actions": [
               {"type": "stroke", "tool": "pen", "color": "#ffffff", "width": 8,
                "points": [{"x": 100, "y": 150, "t": 0}, {"x": 300, "y": 150, "t": 1000}]},
               {"type": "stroke", "tool": "fill", "color": "#ef3b3f", "width": 1,
                "points": [{"x": 200, "y": 100, "t": 1100}]}]}}
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={"width": 800, "height": 600})
        page.route("**/static/**", serve_assets)
        page.route("**/drawing/overlay/test", lambda route: route.fulfill(body=html, content_type="text/html"))
        page.route("**/drawing/overlay/test/next*", lambda route: route.fulfill(json={
            "playback": None if "current=" in route.request.url else job, "current_id": "1", "options": options.model_dump()}))
        page.goto("http://localhost/drawing/overlay/test")
        boundary = page.evaluate("""() => {
            const probe = document.createElement('canvas');
            probe.width = 400; probe.height = 300;
            const ctx = probe.getContext('2d');
            const ring = width => {
                const points = [];
                for (let i = 0; i <= 72; i++) {
                    const angle = i / 72 * Math.PI * 2;
                    points.push({x: 200 + Math.cos(angle) * 110, y: 150 + Math.sin(angle) * 90, t: i * 10});
                }
                return {width: 400, height: 300,
                    actions: [{type: 'stroke', tool: 'pen', color: '#8b4db0', width, points}]};
            };
            // 굵은 폐곡선 안쪽을 같은 색으로 채우면 경계에 빈 틈이 남지 않아야 한다.
            DrawingCanvas.render(probe, ring(20), Infinity, true);
            DrawingCanvas.fill(ctx, 200, 150, '#8b4db0');
            const pixels = ctx.getImageData(0, 0, 400, 300).data;
            let unfilled = 0;
            for (let y = 0; y < 300; y++) for (let x = 0; x < 400; x++) {
                if (Math.hypot((x - 200) / 110, (y - 150) / 90) > 0.95) continue;
                if (pixels[(y * 400 + x) * 4 + 3] < 255) unfilled++;
            }
            // 가장 가는 선도 끊기지 않아 바깥 채우기가 안쪽으로 새지 않아야 한다.
            DrawingCanvas.render(probe, ring(1), Infinity, true);
            DrawingCanvas.fill(ctx, 5, 5, '#ef3b3f');
            const leaked = ctx.getImageData(200, 150, 1, 1).data[3] > 0;
            // 지우개가 지운 가장자리는 되살아나지 않고, 캔버스에 반투명 픽셀이 남지 않아야 한다.
            const from = {x: 150, y: 60}, to = {x: 250, y: 240}, half = 15;
            DrawingCanvas.render(probe, {width: 400, height: 300, actions: [
                {type: 'stroke', tool: 'pen', color: '#8b4db0', width: 60,
                 points: [{x: 60, y: 150, t: 0}, {x: 340, y: 150, t: 100}]},
                {type: 'stroke', tool: 'eraser', color: '#ffffff', width: 30,
                 points: [{...from, t: 200}, {...to, t: 300}]}]}, Infinity, true);
            const erased = ctx.getImageData(0, 0, 400, 300).data;
            let survived = 0, translucent = 0;
            const dx = to.x - from.x, dy = to.y - from.y, span = dx * dx + dy * dy;
            for (let y = 0; y < 300; y++) for (let x = 0; x < 400; x++) {
                const alpha = erased[(y * 400 + x) * 4 + 3];
                if (alpha !== 0 && alpha !== 255) translucent++;
                const along = Math.max(0, Math.min(1, ((x - from.x) * dx + (y - from.y) * dy) / span));
                if (Math.hypot(x - from.x - along * dx, y - from.y - along * dy) >= half) continue;
                if (alpha !== 0) survived++;   // 지우개가 덮은 반경 안은 완전히 지워져야 한다
            }
            return {unfilled, leaked, survived, translucent};
        }""")
        assert boundary == {"unfilled": 0, "leaked": False, "survived": 0, "translucent": 0}
        page.locator("#drawingOverlay").wait_for(state="visible")
        page.wait_for_function("""() => {
            const ctx = document.getElementById('replayCanvas').getContext('2d');
            const filled = ctx.getImageData(200, 100, 1, 1).data;
            const whiteStroke = ctx.getImageData(200, 150, 1, 1).data;
            return filled[0] > 220 && filled[1] < 90 && filled[2] < 90 && filled[3] === 255 &&
                whiteStroke[0] > 220 && whiteStroke[1] > 220 && whiteStroke[2] > 220 && whiteStroke[3] === 255;
        }""", timeout=6000)
        browser.close()


@pytest.mark.parametrize("width", [375, 1280])
def test_drawing_pages_fit_mobile_and_dashboard_preview_does_not_consume_queue(width, tmp_path):
    options = DrawingDonationOptions(enabled=True)
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": 1000})
        page.route("**/static/**", serve_assets)
        html = templates.get_template("dashboard_drawing.html").render(
            channel=SimpleNamespace(channel_name="테스트 스트리머"), options=options,
            drawing_url="http://localhost/drawing/chzzk/channel", overlay_url="http://localhost/drawing/overlay/test",
            preview_path="/drawing/overlay/test?preview=1")
        page.route("**/auth/dashboard/drawing", lambda route: route.fulfill(body=html, content_type="text/html"))
        overlay_html = templates.get_template("drawing_overlay.html").render(
            options=options.model_dump(), poll_path="/drawing/overlay/test/next", preview=True)
        page.route("**/drawing/overlay/test?preview=1", lambda route: route.fulfill(body=overlay_html, content_type="text/html"))
        requests = []
        page.on("request", lambda request: requests.append(request.url))
        page.goto("http://localhost/auth/dashboard/drawing")
        page.locator("#testDrawing").click()
        frame = page.frame_locator("#drawingPreview")
        frame.locator("#drawingOverlay").wait_for(state="visible")
        bounds = frame.locator("#drawingOverlay").evaluate("element => ({bottom: element.getBoundingClientRect().bottom, height: innerHeight, width: element.getBoundingClientRect().width, donorHeight: document.getElementById('drawingDonor').getBoundingClientRect().height})")
        assert bounds["bottom"] <= bounds["height"], bounds
        assert page.locator('[name="display_width"]').count() == 0
        page.locator('[name="canvas_width"]').fill("1280")
        page.locator('[name="canvas_height"]').fill("720")
        page.locator('[name="show_donor"]').uncheck()
        page.locator("#testDrawing").click()
        frame.locator("#drawingDonor").wait_for(state="hidden")
        assert frame.locator("#replayCanvas").evaluate("canvas => [canvas.width, canvas.height]") == [1280, 720]
        assert not any("/next" in url for url in requests)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.screenshot(path=str(tmp_path / f"drawing-dashboard-{width}.png"), full_page=True)
        browser.close()


@pytest.mark.parametrize("size,show_donor", [((1280, 720), False), ((800, 600), True), ((600, 900), False)])
def test_overlay_uses_full_viewport_preserves_picture_ratio_and_resizes(size, show_donor):
    options = DrawingDonationOptions(enabled=True, canvas_width=size[0], canvas_height=size[1], show_donor=show_donor)
    html = templates.get_template("drawing_overlay.html").render(
        options=options.model_dump(), poll_path="/drawing/overlay/test/next", preview=False)
    job = {"id": "1", "nickname": "후원자", "amount": 1000, "elapsed_ms": 0, "options": options.model_dump(),
           "recording": {"width": size[0], "height": size[1], "actions": [
               {"type": "stroke", "tool": "pen", "color": "#246544", "width": 6, "points": [{"x": 10, "y": 10, "t": 0}]}]}}
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 720})
        page.route("**/static/**", serve_assets)
        page.route("**/drawing/overlay/test", lambda route: route.fulfill(body=html, content_type="text/html"))
        page.route("**/drawing/overlay/test/next*", lambda route: route.fulfill(json={
            "playback": None if "current=" in route.request.url else job, "current_id": "1", "options": options.model_dump()}))
        page.goto("http://localhost/drawing/overlay/test")
        page.locator("#drawingOverlay").wait_for(state="visible")
        measure = """() => {
            const overlay = document.getElementById('drawingOverlay').getBoundingClientRect();
            const canvas = document.getElementById('replayCanvas').getBoundingClientRect();
            return {overlayWidth: overlay.width, overlayHeight: overlay.height, width: canvas.width, height: canvas.height,
                top: canvas.top, bottom: canvas.bottom, left: canvas.left, right: canvas.right};
        }"""
        def check(width, height):
            bounds = page.evaluate(measure)
            assert (bounds["overlayWidth"], bounds["overlayHeight"]) == (width, height)
            assert abs(bounds["width"] / bounds["height"] - size[0] / size[1]) < 0.01
            assert bounds["left"] >= -1 and bounds["top"] >= -1
            assert bounds["right"] <= width + 1 and bounds["bottom"] <= height + 1
            if not show_donor:
                assert abs(bounds["width"] - width) < 1 or abs(bounds["height"] - height) < 1
        check(1280, 720)
        assert page.locator("#drawingDonor").is_visible() == show_donor
        page.set_viewport_size({"width": 900, "height": 600})
        page.wait_for_function("""() => {
            const bounds = document.getElementById('replayCanvas').getBoundingClientRect();
            return bounds.top >= -1 && bounds.left >= -1 && bounds.right <= innerWidth + 1 && bounds.bottom <= innerHeight + 1;
        }""")
        check(900, 600)
        browser.close()


@pytest.mark.parametrize("mode", ["editor", "dashboard"])
def test_save_errors_from_application_handler_are_shown_and_can_be_retried(mode):
    options = DrawingDonationOptions(enabled=True)
    editor = mode == "editor"
    path = "/drawing/chzzk/channel" if editor else "/auth/dashboard/drawing"
    template = "drawing.html" if editor else "dashboard_drawing.html"
    html = templates.get_template(template).render(
        channel=SimpleNamespace(channel_name="테스트 스트리머", platform_channel_id="channel"), options=options,
        drawing_url="/drawing/chzzk/channel", overlay_url="/drawing/overlay/test",
        preview_path="/drawing/overlay/test?preview=1")
    message = "그림 저장 요청이 너무 많습니다. 잠시 후 다시 시도해주세요." if editor else "등록된 채널 정보를 찾을 수 없습니다."
    attempts = []
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page()
        page.route("**/static/**", serve_assets)
        def endpoint(route: Route):
            if route.request.method == "GET":
                route.fulfill(body=html, content_type="text/html")
                return
            attempts.append(route.request.post_data_json)
            if len(attempts) == 1:
                route.fulfill(status=429 if editor else 403, json={"error": message, "status_code": 429 if editor else 403},
                              headers={"Retry-After": "60"})
            else:
                route.fulfill(json={"hashtag": "#mw-" + "a" * 24} if editor else {"status": "success"})
        page.route("**" + path, endpoint)
        if not editor:
            page.route("**/drawing/overlay/**", lambda route: route.fulfill(body="<html></html>", content_type="text/html"))
        page.goto("http://localhost" + path)
        if editor:
            live_status = page.locator("#drawingStatus")
            assert live_status.get_attribute("role") == "status"
            assert live_status.get_attribute("aria-live") == "polite"
            assert live_status.inner_text() == ""
            assert live_status.evaluate("e => getComputedStyle(e).display") != "none"
            page.locator("#drawingCanvas").click(position={"x": 50, "y": 50})
        button = page.locator("#saveDrawing" if editor else '#drawingSettings [type="submit"]')
        status_id = "drawingStatus" if editor else "settingsStatus"
        button.click()
        page.wait_for_function("([id, message]) => document.getElementById(id).textContent === message", arg=[status_id, message])
        assert page.locator("#" + status_id).is_visible()
        assert button.is_enabled()
        button.click()
        if editor:
            page.wait_for_function("document.getElementById('drawingTag').value.startsWith('#mw-')")
            assert attempts[0]["save_key"] == attempts[1]["save_key"]
            assert page.locator("#drawingStatus").inner_text() == ""
            assert page.locator("#drawingStatus").evaluate("e => getComputedStyle(e).display") != "none"
        else:
            page.wait_for_function("document.getElementById('settingsStatus').textContent === '설정을 저장했어요.'")
        assert len(attempts) == 2
        browser.close()


@pytest.mark.parametrize("width", [375, 1280])
def test_optional_live_background_is_not_saved_and_refresh_errors_are_recoverable(width, tmp_path):
    options = DrawingDonationOptions(enabled=True)
    html = templates.get_template("drawing.html").render(
        channel=SimpleNamespace(channel_name="테스트 스트리머", platform_channel_id="channel"), options=options)
    backgrounds = []
    saved = []
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": 1000})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.clock.install()
        page.route("**/static/**", serve_assets)
        def editor(route: Route):
            if route.request.method == "GET":
                route.fulfill(body=html, content_type="text/html")
            else:
                saved.append(DrawingSaveRequest.model_validate(route.request.post_data_json))
                route.fulfill(json={"hashtag": "#mw-" + "d" * 24})
        def background(route: Route):
            backgrounds.append(route.request.url)
            if len(backgrounds) == 2:
                route.fulfill(status=429, json={"error": "방송 이미지 요청이 너무 빠릅니다."}, headers={"Retry-After": "1"})
            else:
                route.fulfill(json={"image_url": None if len(backgrounds) == 3 else
                                    "https://thumbnail.example/image_720.jpg" if len(backgrounds) != 4 else
                                    "https://thumbnail.example/broken.jpg"})
        page.route("**/drawing/chzzk/channel", editor)
        page.route("**/drawing/chzzk/channel/background", background)
        # CORS 헤더가 없는 외부 이미지도 HTML 배경으로만 표시되어 캔버스 저장을 방해하지 않는다.
        page.route("https://thumbnail.example/**", lambda route: route.fulfill(
            status=404 if "broken" in route.request.url else 200, content_type="image/svg+xml",
            body='invalid-image' if "broken" in route.request.url else
                 '<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720"><rect width="1280" height="720" fill="#698bb2"/></svg>'))
        page.goto("http://localhost/drawing/chzzk/channel")
        canvas = page.locator("#drawingCanvas")
        mode = page.locator("#canvasBackgroundMode")
        image = page.locator("#liveBackgroundImage")
        refresh = page.locator("#refreshLiveBackground")
        status = page.locator("#liveBackgroundStatus")
        blank = canvas.evaluate("c => c.toDataURL()")
        assert mode.input_value() == "color" and not backgrounds
        assert page.locator('button[data-background-mode="color"]').get_attribute("aria-pressed") == "true"
        assert page.locator("#liveBackgroundControls").is_hidden()
        page.locator('[data-tool="eraser"]').click()
        page.locator("#drawingBackgroundSettings").evaluate("element => element.open = true")
        page.get_by_role("button", name="배경 파랑", exact=True).click()
        assert page.locator("#canvasBackgroundColor").input_value() == "#2f6ee5"
        assert page.locator('[data-tool="eraser"]').get_attribute("aria-pressed") == "true"
        assert page.locator("#penColor").input_value() == "#25453c"
        assert page.locator("#drawingCanvasStage").evaluate("e => getComputedStyle(e).backgroundColor") == "rgb(47, 110, 229)"
        page.locator("#canvasBackgroundColor").fill("#20362e")
        assert page.locator('[data-background-color][aria-pressed="true"]').count() == 0
        choose_background(page, "transparent")
        assert "conic-gradient" in page.locator("#drawingCanvasStage").evaluate("e => getComputedStyle(e).backgroundImage")
        assert page.locator("#backgroundColorControl").is_hidden()
        assert canvas.evaluate("c => c.toDataURL()") == blank
        assert not backgrounds
        choose_background(page, "live")
        assert "conic-gradient" in page.locator("#drawingCanvasStage").evaluate("e => getComputedStyle(e).backgroundImage")
        image.wait_for(state="visible")
        assert refresh.is_disabled()
        refresh.dispatch_event("click")
        assert len(backgrounds) == 1
        assert image.evaluate("i => i.naturalWidth") == 1280
        assert "image_720.jpg" in (image.get_attribute("src") or "")
        assert image.evaluate("i => getComputedStyle(i).opacity") == "0.5"
        assert canvas.evaluate("c => c.toDataURL()") == blank
        page.locator('[data-color="#ffffff"]').click()
        canvas.click(position={"x": 30, "y": 30})
        picture = canvas.evaluate("c => c.toDataURL()")
        page.locator("#liveBackgroundTransparency").fill("100")
        assert image.evaluate("i => getComputedStyle(i).opacity") == "0"
        assert page.locator("#liveBackgroundTransparencyValue").text_content() == "100%"
        page.locator("#liveBackgroundTransparency").fill("0")
        assert image.evaluate("i => getComputedStyle(i).opacity") == "1"
        assert canvas.evaluate("c => c.toDataURL()") == picture
        choose_background(page, "color")
        assert image.is_hidden()
        assert page.locator("#drawingCanvasStage").evaluate("e => getComputedStyle(e).backgroundColor") == "rgb(32, 54, 46)"
        choose_background(page, "live")
        assert image.is_visible() and len(backgrounds) == 1
        page.locator("#liveBackgroundTransparency").fill("50")
        page.locator("#saveDrawing").click()
        page.wait_for_function("document.getElementById('drawingTag').value.startsWith('#mw-')")
        assert saved[0].final_png == picture
        assert len(saved[0].recording.actions) == 1
        assert canvas.evaluate("c => c.getContext('2d').getImageData(700,500,1,1).data[3]") == 0
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.screenshot(path=str(tmp_path / f"live-background-{width}.png"), full_page=True)
        choose_background(page, "transparent")
        assert image.is_hidden()
        assert canvas.evaluate("c => c.toDataURL()") == picture
        assert page.locator("#drawingResult").is_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.screenshot(path=str(tmp_path / f"transparent-background-{width}.png"), full_page=True)
        choose_background(page, "live")
        page.clock.fast_forward(5100)
        assert refresh.is_enabled()
        refresh.click()
        page.wait_for_function("document.getElementById('liveBackgroundStatus').textContent.includes('1초 후')")
        assert "요청이 너무 빠릅니다" in status.inner_text()
        assert refresh.is_disabled() and image.is_visible()
        page.clock.fast_forward(1100)
        page.wait_for_function("!document.getElementById('refreshLiveBackground').disabled")
        refresh.click()
        page.wait_for_function("document.getElementById('liveBackgroundStatus').textContent.includes('이미지가 없어요')")
        assert image.is_hidden() and refresh.is_disabled()
        page.clock.fast_forward(5100)
        refresh.click()
        page.wait_for_function("document.getElementById('liveBackgroundStatus').textContent.includes('불러오지 못했어요')")
        assert refresh.is_disabled() and image.is_hidden()
        page.clock.fast_forward(5100)
        refresh.click()
        image.wait_for(state="visible")
        assert canvas.evaluate("c => c.toDataURL()") == picture
        assert page.locator("#drawingResult").is_visible()
        assert refresh.is_disabled()
        assert not errors
        browser.close()


def test_live_background_loaded_after_switching_to_color_stays_hidden():
    options = DrawingDonationOptions(enabled=True)
    html = templates.get_template("drawing.html").render(
        channel=SimpleNamespace(channel_name="테스트", platform_channel_id="channel"), options=options)
    pending: list[Route] = []
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page()
        page.route("**/static/**", serve_assets)
        page.route("**/drawing/chzzk/channel", lambda route: route.fulfill(body=html, content_type="text/html"))
        page.route("**/drawing/chzzk/channel/background", lambda route: pending.append(route))
        page.route("https://thumbnail.example/**", lambda route: route.fulfill(content_type="image/svg+xml",
            body='<svg xmlns="http://www.w3.org/2000/svg" width="800" height="600"/>'))
        page.goto("http://localhost/drawing/chzzk/channel")
        with page.expect_request("**/drawing/chzzk/channel/background"):
            choose_background(page, "live")
        choose_background(page, "color")
        assert len(pending) == 1
        pending[0].fulfill(json={"image_url": "https://thumbnail.example/image_720.jpg"})
        page.wait_for_function("document.getElementById('liveBackgroundImage').naturalWidth > 0")
        assert page.locator("#liveBackgroundImage").is_hidden()
        assert page.locator("#liveBackgroundControls").is_hidden()
        browser.close()


@pytest.mark.parametrize("status_code,body", [(429, "<html>Too many requests</html>"),
                                              (503, "<html>Service unavailable</html>"),
                                              (429, ""), (503, "null")])
def test_live_background_non_json_errors_keep_retry_after_and_can_be_retried(status_code, body):
    options = DrawingDonationOptions(enabled=True)
    html = templates.get_template("drawing.html").render(
        channel=SimpleNamespace(channel_name="테스트", platform_channel_id="channel"), options=options)
    requests = []
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page()
        page.clock.install()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route("**/static/**", serve_assets)
        page.route("**/drawing/chzzk/channel", lambda route: route.fulfill(body=html, content_type="text/html"))
        def background(route: Route):
            requests.append(route.request.url)
            if len(requests) == 1:
                route.fulfill(status=status_code, body=body, content_type="text/html", headers={"Retry-After": "2"})
            else:
                route.fulfill(json={"image_url": None})
        page.route("**/drawing/chzzk/channel/background", background)
        page.goto("http://localhost/drawing/chzzk/channel")
        page.locator("#drawingCanvas").click(position={"x": 30, "y": 30})
        picture = page.locator("#drawingCanvas").evaluate("c => c.toDataURL()")
        choose_background(page, "live")
        page.wait_for_function("document.getElementById('liveBackgroundStatus').textContent.includes('2초 후')")
        refresh = page.locator("#refreshLiveBackground")
        assert "조회에 실패" in page.locator("#liveBackgroundStatus").inner_text()
        assert refresh.is_disabled()
        refresh.dispatch_event("click")
        assert len(requests) == 1
        page.clock.fast_forward(1000)
        assert refresh.is_disabled()
        page.clock.fast_forward(1100)
        assert refresh.is_enabled()
        refresh.click()
        page.wait_for_function("document.getElementById('liveBackgroundStatus').textContent.includes('이미지가 없어요')")
        assert len(requests) == 2 and refresh.is_disabled()
        assert page.locator("#drawingCanvas").evaluate("c => c.toDataURL()") == picture
        page.clock.fast_forward(5100)
        assert refresh.is_enabled()
        assert not errors
        browser.close()


@pytest.mark.parametrize("mode", ["transparent", "live"])
def test_initial_and_restored_background_mode_matches_controls(mode):
    options = DrawingDonationOptions(enabled=True)
    html = templates.get_template("drawing.html").render(
        channel=SimpleNamespace(channel_name="테스트", platform_channel_id="channel"), options=options)
    html = html.replace(f'<option value="{mode}">', f'<option value="{mode}" selected>')
    requests = []
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page()
        page.route("**/static/**", serve_assets)
        page.route("**/drawing/chzzk/channel", lambda route: route.fulfill(body=html, content_type="text/html"))
        def background(route: Route):
            requests.append(route.request.url)
            route.fulfill(json={"image_url": None})
        page.route("**/drawing/chzzk/channel/background", background)
        page.goto("http://localhost/drawing/chzzk/channel")
        page.locator("#drawingBackgroundSettings").evaluate("element => element.open = true")
        assert page.locator("#drawingCanvasStage").get_attribute("data-background-mode") == mode
        assert page.locator(f'button[data-background-mode="{mode}"]').get_attribute("aria-pressed") == "true"
        assert page.locator("#backgroundColorControl").is_hidden()
        assert page.locator("#liveBackgroundControls").is_visible() == (mode == "live")
        if mode == "live":
            page.wait_for_function("document.getElementById('liveBackgroundStatus').textContent.includes('이미지가 없어요')")
            assert len(requests) == 1
        else:
            assert not requests
            assert "conic-gradient" in page.locator("#drawingCanvasStage").evaluate("e => getComputedStyle(e).backgroundImage")
        page.evaluate("""() => {
            document.getElementById('canvasBackgroundMode').value = 'color';
            window.dispatchEvent(new PageTransitionEvent('pageshow', {persisted: true}));
        }""")
        assert page.locator("#drawingCanvasStage").get_attribute("data-background-mode") == "color"
        assert page.locator('button[data-background-mode="color"]').get_attribute("aria-pressed") == "true"
        assert page.locator("#backgroundColorControl").is_visible()
        assert page.locator("#liveBackgroundControls").is_hidden()
        assert page.locator("#liveBackgroundImage").is_hidden()
        browser.close()


@pytest.mark.parametrize("width", [375, 1280])
def test_redesigned_editor_history_clear_confirmation_and_saved_editing(width, tmp_path):
    options = DrawingDonationOptions(enabled=True)
    html = templates.get_template("drawing.html").render(
        channel=SimpleNamespace(channel_name="테스트 스트리머", platform_channel_id="channel"), options=options)
    saved = []
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": 1100})
        page.clock.install()
        page.add_init_script("""Object.defineProperty(navigator, 'clipboard', {value: {
            writeText: async value => { window.copiedDrawingTag = value; }
        }});""")
        page.route("**/static/**", serve_assets)
        def editor(route: Route):
            if route.request.method == "GET":
                route.fulfill(body=html, content_type="text/html")
            else:
                saved.append(DrawingSaveRequest.model_validate(route.request.post_data_json))
                route.fulfill(json={"hashtag": "#mw-" + ("a" if len(saved) == 1 else "b") * 24})
        page.route("**/drawing/chzzk/channel", editor)
        page.goto("http://localhost/drawing/chzzk/channel")
        canvas = page.locator("#drawingCanvas")
        picture = lambda: canvas.evaluate("c => c.toDataURL()")
        blank = picture()
        assert page.locator("#saveDrawing").is_disabled()
        assert page.locator("#undoDrawing").is_disabled() and page.locator("#redoDrawing").is_disabled()
        assert page.locator("#emptyDrawingHint").is_visible()
        page.locator("#penWidth").fill("18")
        page.locator('[data-color="#f6a21a"]').click()
        assert page.locator("#brushPreviewDot").evaluate("e => [e.style.width, e.style.backgroundColor]") == ["18px", "rgb(246, 162, 26)"]
        canvas.click(position={"x": 30, "y": 80})
        first = picture()
        page.clock.fast_forward(1100)
        assert page.locator("#recordingTime, #recordingProgress, #recordingState").count() == 0
        assert page.locator("#emptyDrawingHint").is_hidden()
        canvas.click(position={"x": 80, "y": 110})
        before_clear = picture()
        page.locator("#undoDrawing").click()
        assert picture() == first
        page.keyboard.press("Control+Shift+z")
        assert picture() == before_clear
        page.keyboard.press("Control+z")
        assert picture() == first
        page.keyboard.press("Control+y")
        assert picture() == before_clear
        page.locator("#clearDrawing").click()
        assert page.get_by_role("dialog", name="그림을 모두 지울까요?").is_visible()
        assert picture() == before_clear
        assert page.locator("#saveDrawing").is_disabled()
        page.keyboard.press("Escape")
        page.wait_for_function("!document.getElementById('saveDrawing').disabled")
        assert picture() == before_clear
        page.locator("#clearDrawing").click()
        page.locator("#confirmClearDrawing").click()
        assert picture() == blank
        assert page.locator("#saveDrawing").is_disabled()
        canvas.click(position={"x": 100, "y": 120})
        after_clear = picture()
        page.clock.fast_forward(1100)
        page.locator("#undoDrawing").click()
        assert picture() == blank
        page.locator("#undoDrawing").click()
        assert picture() == before_clear
        page.locator("#redoDrawing").click()
        assert picture() == blank
        page.locator("#redoDrawing").click()
        assert picture() == after_clear
        page.locator("#saveDrawing").click()
        page.locator("#drawingResult").wait_for(state="visible")
        assert len(saved[0].recording.actions) == 1 and saved[0].final_png == after_clear
        assert page.locator('[data-step="2"]').get_attribute("aria-current") == "step"
        assert page.locator("#drawingSaveControls").is_hidden()
        canvas.click(position={"x": 150, "y": 120})
        page.keyboard.press("Control+z")
        assert picture() == after_clear
        page.locator("#copyDrawingTag").click()
        page.wait_for_function("document.getElementById('copyDrawingLabel').textContent === '복사했어요'")
        assert page.evaluate("window.copiedDrawingTag") == page.locator("#drawingTag").input_value()
        assert page.locator('[data-step="3"]').get_attribute("aria-current") == "step"
        page.screenshot(path=str(tmp_path / f"redesigned-saved-{width}.png"), full_page=True)
        page.locator("#editSavedDrawing").click()
        assert page.locator("#drawingResult").is_hidden()
        assert page.locator("#drawingSaveControls").is_visible()
        canvas.click(position={"x": 150, "y": 140})
        edited = picture()
        assert edited != after_clear and page.locator("#redoDrawing").is_disabled()
        page.locator("#saveDrawing").click()
        page.locator("#drawingResult").wait_for(state="visible")
        assert len(saved) == 2 and saved[1].save_key != saved[0].save_key
        assert len(saved[1].recording.actions) == 2 and saved[1].final_png == edited
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        browser.close()


def test_recording_excludes_idle_and_undone_time_and_keeps_limit_and_failed_copy():
    options = DrawingDonationOptions(enabled=True)
    html = templates.get_template("drawing.html").render(
        channel=SimpleNamespace(channel_name="테스트", platform_channel_id="channel"), options=options)
    saved = []
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page()
        page.clock.install()
        page.add_init_script("""window.drawingTestTime = 0;
            performance.now = () => window.drawingTestTime;
            Object.defineProperty(navigator, 'clipboard', {value: {
            writeText: async () => { throw new Error('denied'); }
        }});""")
        page.route("**/static/**", serve_assets)
        def editor(route: Route):
            if route.request.method == "GET":
                route.fulfill(body=html, content_type="text/html")
            else:
                saved.append(DrawingSaveRequest.model_validate(route.request.post_data_json))
                route.fulfill(json={"hashtag": "#mw-" + "c" * 24})
        page.route("**/drawing/chzzk/channel", editor)
        page.goto("http://localhost/drawing/chzzk/channel")
        canvas = page.locator("#drawingCanvas")
        def advance(duration: int) -> None:
            page.evaluate("duration => { window.drawingTestTime += duration; }", duration)
            page.clock.fast_forward(duration)

        def draw(duration: int, y: int) -> None:
            canvas.scroll_into_view_if_needed()
            box = canvas.bounding_box()
            assert box
            page.mouse.move(box["x"] + 80, box["y"] + y)
            page.mouse.down()
            advance(duration)
            page.mouse.move(box["x"] + 150, box["y"] + y)
            page.mouse.up()

        draw(1000, 80)
        advance(600100)
        assert canvas.get_attribute("aria-disabled") == "false"
        assert page.locator("#recordingTime, #recordingProgress, #recordingState").count() == 0
        draw(2000, 100)
        page.locator("#saveDrawing").click()
        page.locator("#drawingResult").wait_for(state="visible")
        actions = saved[0].recording.actions
        assert len(actions) == 2 and all(isinstance(action, Stroke) for action in actions)
        times = [[point.t for point in action.points] for action in actions if isinstance(action, Stroke)]
        assert times == [[0, 1000], [1000, 3000]]
        page.locator("#editSavedDrawing").click()
        page.locator("#undoDrawing").click()
        advance(600100)
        draw(599100, 120)
        picture = canvas.evaluate("c => c.toDataURL()")
        assert canvas.get_attribute("aria-disabled") == "true"
        assert "기록 한도" in page.locator("#drawingStatus").inner_text()
        canvas.click(position={"x": 150, "y": 150})
        assert canvas.evaluate("c => c.toDataURL()") == picture
        page.locator("#undoDrawing").click()
        assert canvas.get_attribute("aria-disabled") == "false"
        page.locator("#redoDrawing").click()
        assert canvas.get_attribute("aria-disabled") == "true"
        assert canvas.evaluate("c => c.toDataURL()") == picture
        assert page.locator("#saveDrawing").is_enabled()
        page.locator("#saveDrawing").click()
        page.locator("#drawingResult").wait_for(state="visible")
        assert len(saved[1].recording.actions) == 2 and saved[1].final_png == picture
        last = saved[1].recording.actions[-1]
        assert isinstance(last, Stroke) and last.points[0].t == 1000 and last.points[-1].t == 600000
        page.locator("#copyDrawingTag").click()
        page.wait_for_function("document.getElementById('drawingStatus').textContent.includes('직접 복사')")
        assert page.locator("#copyDrawingLabel").inner_text() == "해시태그 복사"
        assert page.locator('[data-step="2"]').get_attribute("aria-current") == "step"
        assert page.locator("#drawingTag").evaluate("e => e.selectionStart === 0 && e.selectionEnd === e.value.length")
        assert canvas.evaluate("c => c.toDataURL()") == picture
        page.locator("#editSavedDrawing").click()
        page.locator("#undoDrawing").click()
        advance(1200000)
        draw(500, 160)
        assert page.locator("#redoDrawing").is_disabled()
        page.locator("#saveDrawing").click()
        page.locator("#drawingResult").wait_for(state="visible")
        last = saved[2].recording.actions[-1]
        assert isinstance(last, Stroke) and last.points[0].t == 1000 and last.points[-1].t == 1500
        browser.close()


@pytest.mark.parametrize("width", [375, 1280])
def test_dashboard_history_thumbnails_paging_replay_and_expiry(width, tmp_path):
    options = DrawingDonationOptions(enabled=True)
    html = templates.get_template("dashboard_drawing_playback.html").render(
        channel=SimpleNamespace(channel_name="테스트 스트리머"), options=options,
        drawing_url="/drawing/chzzk/channel", overlay_url="/drawing/overlay/test", preview_path="/drawing/overlay/test?preview=1")
    now = datetime.now(timezone.utc)
    nickname = '<img src=x onerror="alert(1)">'
    def item(identity, name, *, drawing_id="shared-drawing", status="done"):
        return {"id": str(identity), "drawing_id": drawing_id, "nickname": name, "amount": 12500,
                "status": status, "played_at": now.isoformat(), "received_at": now.isoformat(),
                "expires_at": (now + timedelta(hours=1)).isoformat(), "replay_status": None}
    items = [item(3, nickname), item(2, "익명"), item(1, "재생 중인 후원자", drawing_id="another-drawing", status="playing")]
    recording = {"width": 400, "height": 300, "actions": [{"type": "stroke", "tool": "pen", "color": "#246544",
        "width": 20, "points": [{"x": 40, "y": 40, "t": 0}, {"x": 120, "y": 40, "t": 1000}]}]}
    state = {"expired": False, "pending": False}
    requests, preview_requests, replays, errors = [], [], [], []
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": 1100})
        page.clock.install(time=now)
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("request", lambda request: requests.append(request.url))
        page.route("**/static/**", serve_assets)
        page.route("**/auth/dashboard/drawing/playback", lambda route: route.fulfill(body=html, content_type="text/html"))
        page.route("**/drawing/overlay/test?preview=1", lambda route: route.fulfill(body="<html></html>", content_type="text/html"))
        def history(route: Route):
            if state["expired"]:
                rows, cursor = [], None
            elif "before=" in route.request.url:
                rows, cursor = items[2:], None
            else:
                rows, cursor = items[:2], "2"
            data = [{**row, "replay_status": "queued" if state["pending"] and row["id"] == "3" else None} for row in rows]
            route.fulfill(json={"items": data, "next_cursor": cursor, "enabled": True,
                                "server_now": (now + timedelta(hours=1, seconds=1) if state["expired"] else now).isoformat()})
        page.route("**/auth/dashboard/drawing/history*", history)
        def preview(route: Route):
            preview_requests.append(route.request.url)
            route.fulfill(json={"recording": recording})
        page.route("**/auth/dashboard/drawing/history/*/recording", preview)
        def replay(route: Route):
            assert route.request.method == "POST"
            replays.append(route.request.url)
            if len(replays) == 1:
                route.fulfill(status=503, json={"error": "재생 요청에 실패했어요. 다시 시도해주세요."})
            else:
                state["pending"] = True
                route.fulfill(json={"id": "100", "status": "queued", "already_queued": False})
        page.route("**/auth/dashboard/drawing/history/*/replay", replay)
        page.goto("http://localhost/auth/dashboard/drawing/playback")
        page.wait_for_function("document.querySelectorAll('.drawing-history-item').length === 2")
        cards = page.locator(".drawing-history-item")
        assert cards.nth(0).locator("strong").inner_text() == nickname
        assert "12,500원" in cards.nth(0).inner_text()
        assert page.locator('img[src="x"]').count() == 0
        for index in range(2):
            cards.nth(index).scroll_into_view_if_needed()
            cards.nth(index).locator("img").wait_for(state="visible")
        assert len(preview_requests) == 1
        expected = page.evaluate("""recording => {
            const source = document.createElement('canvas'); source.width = recording.width; source.height = recording.height;
            DrawingCanvas.render(source, recording, Infinity, true);
            const preview = document.createElement('canvas'); preview.width = 240; preview.height = 180;
            preview.getContext('2d').drawImage(source, 0, 0, 240, 180); return preview.toDataURL();
        }""", recording)
        assert cards.nth(0).locator("img").get_attribute("src") == expected
        assert "conic-gradient" in cards.nth(0).locator(".drawing-history-picture").evaluate("e => getComputedStyle(e).backgroundImage")
        page.locator("#moreDrawingHistory").click()
        page.wait_for_function("document.querySelectorAll('.drawing-history-item').length === 3")
        assert page.locator("#moreDrawingHistory").is_hidden()
        assert cards.nth(2).get_by_role("button", name="재생 중인 후원자님의 후원 그림 방송에서 다시 재생").is_disabled()
        button = cards.nth(0).get_by_role("button", name=f"{nickname}님의 후원 그림 방송에서 다시 재생")
        button.click()
        page.wait_for_function("document.getElementById('drawingHistoryStatus').textContent.includes('실패했어요')")
        assert button.is_enabled()
        button.click()
        page.wait_for_function("document.getElementById('drawingHistoryStatus').textContent.includes('대기열에 추가했어요')")
        assert button.is_disabled() and button.inner_text() == "다시 재생 대기 중"
        button.dispatch_event("click")
        assert len(replays) == 2
        assert not any("/next" in url for url in requests)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.locator(".drawing-history").screenshot(path=str(tmp_path / f"drawing-history-{width}.png"))
        state["expired"] = True
        page.clock.fast_forward(3601000)
        page.wait_for_function("document.querySelectorAll('.drawing-history-item').length === 0")
        assert page.locator("#drawingHistoryEmpty").is_visible()
        assert not errors
        browser.close()


def test_dashboard_history_and_preview_failures_retry_and_expired_replay_is_removed():
    options = DrawingDonationOptions(enabled=False)
    html = templates.get_template("dashboard_drawing_playback.html").render(
        channel=SimpleNamespace(channel_name="테스트"), options=options,
        drawing_url="/drawing/chzzk/channel", overlay_url="/drawing/overlay/test", preview_path="/drawing/overlay/test?preview=1")
    now = datetime.now(timezone.utc)
    item = {"id": "1", "drawing_id": "drawing", "nickname": "시청자", "amount": 1000, "status": "done",
            "played_at": now.isoformat(), "expires_at": (now + timedelta(hours=1)).isoformat(), "replay_status": None}
    requests, preview_requests, errors = [], [], []
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route("**/static/**", serve_assets)
        def settings(route: Route):
            if route.request.method == "GET":
                route.fulfill(body=html, content_type="text/html")
            else:
                route.fulfill(json={"status": "success", "options": route.request.post_data_json})
        page.route("**/auth/dashboard/drawing/playback", settings)
        page.route("**/drawing/overlay/test?preview=1", lambda route: route.fulfill(body="<html></html>", content_type="text/html"))
        def history(route: Route):
            requests.append(route.request.url)
            if len(requests) == 1:
                route.fulfill(status=503, body="<html>Unavailable</html>", content_type="text/html")
            else:
                route.fulfill(json={"items": [item], "next_cursor": None, "enabled": False, "server_now": now.isoformat()})
        page.route("**/auth/dashboard/drawing/history", history)
        def preview(route: Route):
            preview_requests.append(route.request.url)
            if len(preview_requests) == 1:
                route.fulfill(status=502, body="Unavailable", content_type="text/html")
            else:
                route.fulfill(json={"recording": {"width": 800, "height": 600, "actions": [{"type": "stroke", "tool": "fill",
                    "color": "#246544", "width": 1, "points": [{"x": 10, "y": 10, "t": 0}]}]}})
        page.route("**/auth/dashboard/drawing/history/1/recording", preview)
        page.route("**/auth/dashboard/drawing/history/1/replay", lambda route: route.fulfill(status=410, json={"error": "그림 보관 시간이 지났습니다."}))
        page.goto("http://localhost/auth/dashboard/drawing/playback")
        page.wait_for_function("document.getElementById('drawingHistoryStatus').textContent.includes('처리하지 못했어요')")
        assert page.locator("#refreshDrawingHistory").is_enabled()
        assert page.locator("#drawingHistoryEmpty").is_hidden()
        page.locator("#refreshDrawingHistory").click()
        card = page.locator(".drawing-history-item")
        card.wait_for(state="visible"); card.scroll_into_view_if_needed()
        card.get_by_role("button", name="미리보기 다시 불러오기").click()
        card.locator("img").wait_for(state="visible")
        assert len(preview_requests) == 2
        replay_button = card.get_by_role("button", name="시청자님의 후원 그림 방송에서 다시 재생")
        assert replay_button.is_disabled()
        page.evaluate("window.dispatchEvent(new CustomEvent('drawing-receiving-state', {detail: {enabled: true}}))")
        assert replay_button.is_enabled()
        replay_button.click()
        page.wait_for_function("document.getElementById('drawingHistoryStatus').textContent.includes('보관 시간이 지났습니다')")
        assert card.count() == 0 and page.locator("#drawingHistoryEmpty").is_visible()
        assert not errors
        browser.close()
