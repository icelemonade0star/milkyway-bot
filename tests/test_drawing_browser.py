from pathlib import Path
from types import SimpleNamespace

import pytest
from jinja2 import Environment, FileSystemLoader

from app.features.drawing_donation.schemas import DrawingDonationOptions, DrawingSaveRequest, Stroke

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Route, sync_playwright
ROOT = Path(__file__).resolve().parents[1]
templates = Environment(loader=FileSystemLoader(ROOT / "app/templates"), autoescape=True)


def serve_assets(route: Route):
    relative = route.request.url.split("/static/", 1)[1].split("?", 1)[0]
    route.fulfill(path=str(ROOT / "app/static" / relative))


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
        overlay.wait_for_function("() => document.getElementById('replayCanvas').getContext('2d').getImageData(80, 140, 1, 1).data[3] > 0", timeout=6000)
        overlay.screenshot(path=str(tmp_path / "drawing-overlay.png"))
        browser.close()


def test_palette_fill_and_ctrl_z_are_editor_only():
    options = DrawingDonationOptions(enabled=True)
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
        page.locator("#clearDrawing").click()
        page.keyboard.press("Control+z")
        assert canvas.evaluate("c => Array.from(c.getContext('2d').getImageData(200,80,1,1).data)")[:3] == [239, 59, 63]
        page.locator("#clearDrawing").click()
        page.locator('[data-color="#2f6ee5"]').click()
        page.locator('[data-tool="fill"]').click()
        page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        page.locator("#saveDrawing").click()
        page.wait_for_function("document.getElementById('drawingTag').value.startsWith('#mw-')")
        assert len(saved) == 1
        assert len(saved[0].recording.actions) == 1
        action = saved[0].recording.actions[0]
        assert isinstance(action, Stroke) and action.tool == "fill" and action.color == "#2f6ee5"
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
            page.locator("#drawingCanvas").click(position={"x": 50, "y": 50})
        button = page.locator("#saveDrawing" if editor else '#drawingSettings [type="submit"]')
        status_id = "drawingStatus" if editor else "settingsStatus"
        button.click()
        page.wait_for_function("([id, message]) => document.getElementById(id).textContent === message", arg=[status_id, message])
        assert button.is_enabled()
        button.click()
        if editor:
            page.wait_for_function("document.getElementById('drawingTag').value.startsWith('#mw-')")
            assert attempts[0]["save_key"] == attempts[1]["save_key"]
        else:
            page.wait_for_function("document.getElementById('settingsStatus').textContent === '설정을 저장했어요.'")
        assert len(attempts) == 2
        browser.close()
