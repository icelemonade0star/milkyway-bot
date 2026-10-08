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
    page.locator(f'button[data-background-mode="{mode}"]').click()


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
        draw((180, 80), (260, 80))
        assert canvas.evaluate("c => Array.from(c.getContext('2d').getImageData(200,80,1,1).data)")[3] == 0
        page.locator("#undoDrawing").click()
        assert canvas.evaluate("c => Array.from(c.getContext('2d').getImageData(200,80,1,1).data)")[:3] == [37, 69, 60]
        page.locator("#clearDrawing").click()
        page.locator("#confirmClearDrawing").click()
        page.locator('[data-tool="pen"]').click()
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
    html = templates.get_template("dashboard_drawing.html").render(
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
        page.route("**/auth/dashboard/drawing", lambda route: route.fulfill(body=html, content_type="text/html"))
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
        page.goto("http://localhost/auth/dashboard/drawing")
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
    html = templates.get_template("dashboard_drawing.html").render(
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
        page.route("**/auth/dashboard/drawing", settings)
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
        page.goto("http://localhost/auth/dashboard/drawing")
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
        page.locator('[name="enabled"]').check()
        page.locator('#drawingSettings [type="submit"]').click()
        page.wait_for_function("document.getElementById('settingsStatus').textContent === '설정을 저장했어요.'")
        assert replay_button.is_enabled()
        replay_button.click()
        page.wait_for_function("document.getElementById('drawingHistoryStatus').textContent.includes('보관 시간이 지났습니다')")
        assert card.count() == 0 and page.locator("#drawingHistoryEmpty").is_visible()
        assert not errors
        browser.close()
