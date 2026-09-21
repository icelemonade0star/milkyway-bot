import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from jinja2 import Environment, FileSystemLoader

from app.features.chat_overlay.schemas import TimerOverlayStyleOptions
from app.features.chat_overlay.service import build_timer_overlay_css
from app.features.chat_overlay.timer import OverlayTimerManager

playwright = pytest.importorskip("playwright.sync_api")
ROOT = Path(__file__).resolve().parents[1]


def run_server(coroutine):
    # Playwright's sync API already owns an event loop on the test thread.
    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(asyncio.run, coroutine).result()


@pytest.fixture(scope="module")
def browser():
    with playwright.sync_playwright() as runtime:
        instance = runtime.chromium.launch()
        yield instance
        instance.close()


def open_timer(browser, options, viewport, fallback=False):
    template = Environment(loader=FileSystemLoader(ROOT / "app/templates")).get_template("timer_overlay.html")
    html = template.render(
        channel=SimpleNamespace(channel_name="Timer Test"),
        timer_css="" if fallback else build_timer_overlay_css(options),
        timer_options=options.model_dump(), overlay_websocket_path="/ws",
    )
    page = browser.new_page(viewport=viewport)

    def route(request):
        name = request.request.url.rsplit("/", 1)[-1]
        if name in {"timer_overlay.js", "overlay_socket.js"}:
            request.fulfill(path=ROOT / "app/static/js" / name, content_type="application/javascript")
        else:
            request.fulfill(body=html, content_type="text/html")

    page.route("http://timer.test/**", route)
    page.add_init_script("""
        window.WebSocket = class {
            constructor() { this.listeners = {}; window.timerSocket = this; }
            addEventListener(name, fn) { this.listeners[name] = fn; }
            close() {}
        };
        window.deliverTimer = payload => window.timerSocket.listeners.message({data: JSON.stringify(payload)});
    """)
    page.goto("http://timer.test/")
    return page


@pytest.mark.parametrize("viewport", [{"width": 1280, "height": 720}, {"width": 375, "height": 667}])
@pytest.mark.parametrize("opacity,delay,fallback", [(100, 0, False), (45, 1, False), (100, 0, True)])
def test_real_fade_and_server_replay(browser, viewport, opacity, delay, fallback):
    options = TimerOverlayStyleOptions(
        timer_auto_delete=True, timer_auto_delete_delay_seconds=delay, timer_global_opacity=opacity,
    )
    page = open_timer(browser, options, viewport, fallback)
    manager = OverlayTimerManager()
    manager.publish_snapshot = AsyncMock()
    try:
        run_server(manager.set_timer("test", "Countdown", 1, True))
        initial = manager.get_snapshot("test")
        assert initial is not None
        samples = page.evaluate("""payload => new Promise(resolve => {
            const node = document.getElementById('timerOverlay');
            const samples = [];
            window.deliverTimer(payload);
            const start = performance.now();
            function sample() {
                const style = getComputedStyle(node);
                samples.push({time: performance.now() - start, opacity: Number(style.opacity), display: style.display});
                if (style.display === 'none' || performance.now() - start > 5000) resolve(samples);
                else requestAnimationFrame(sample);
            }
            requestAnimationFrame(sample);
        })""", {"type": "timer", "action": "snapshot", "timer": initial})
        base = opacity / 100
        assert samples[0]["opacity"] == pytest.approx(base, abs=0.01)
        assert samples[-1]["display"] == "none"
        fading = [sample for sample in samples if sample["display"] != "none" and 0.01 < sample["opacity"] < base - 0.01]
        assert len(fading) >= 3
        assert fading[0]["opacity"] > fading[-1]["opacity"]
        assert fading[0]["time"] >= initial["remaining_ms"] + delay * 1000 - 50
        print(f"viewport={viewport['width']}, opacity={opacity}, delay={delay}, fallback={fallback}: "
              f"fade {fading[0]['opacity']:.3f} -> {fading[-1]['opacity']:.3f}, hidden at {samples[-1]['time']:.0f}ms")
        run_server(manager.play("test"))
        replay = manager.get_snapshot("test")
        assert replay is not None
        assert replay["timer_id"] != initial["timer_id"]
        page.evaluate("payload => window.deliverTimer(payload)", {"type": "timer", "action": "snapshot", "timer": replay})
        page.wait_for_function("getComputedStyle(document.getElementById('timerOverlay')).display === 'flex'")
        assert page.locator("#timerTime").inner_text() == "00:01"
        assert page.locator("#timerOverlay").evaluate("node => Number(getComputedStyle(node).opacity)") == pytest.approx(base)
        assert not page.locator("#timerOverlay").evaluate("node => node.classList.contains('is-fading')")
    finally:
        page.close()


def test_replay_during_fade_and_manual_delete(browser):
    page = open_timer(browser, TimerOverlayStyleOptions(timer_auto_delete=True, timer_auto_delete_delay_seconds=0), {"width": 1280, "height": 720})
    try:
        page.evaluate("window.deliverTimer({type: 'timer', timer: {timer_id: 'first', remaining_ms: 250, running: true}})")
        page.wait_for_function("document.getElementById('timerOverlay').classList.contains('is-fading')")
        page.evaluate("window.deliverTimer({type: 'timer', timer: {timer_id: 'next', remaining_ms: 5000, running: true}})")
        page.wait_for_timeout(800)
        assert page.locator("#timerOverlay").is_visible()
        assert page.locator("#timerOverlay").evaluate("node => getComputedStyle(node).opacity") == "1"
        page.evaluate("window.deliverTimer({type: 'timer', action: 'delete'})")
        assert not page.locator("#timerOverlay").is_visible()
    finally:
        page.close()


def test_auto_delete_disabled_keeps_finished_timer_visible(browser):
    page = open_timer(browser, TimerOverlayStyleOptions(timer_auto_delete=False), {"width": 1280, "height": 720})
    try:
        page.evaluate("window.deliverTimer({type: 'timer', timer: {remaining_ms: 200, running: true}})")
        page.wait_for_timeout(1000)
        assert page.locator("#timerTime").inner_text() == "00:00"
        assert page.locator("#timerOverlay").is_visible()
        assert page.locator("#timerOverlay").evaluate("node => getComputedStyle(node).opacity") == "1"
    finally:
        page.close()
