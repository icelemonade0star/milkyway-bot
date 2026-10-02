from pathlib import Path
from types import SimpleNamespace

import pytest
from jinja2 import Environment, FileSystemLoader

from app.features.chat_overlay.schemas import ChatOverlayStyleOptions
from app.features.chat_overlay.service import build_overlay_css

playwright = pytest.importorskip("playwright.sync_api")
ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("width", [375, 500, 1280])
@pytest.mark.parametrize("position", ["bottom-left", "bottom-right", "center"])
@pytest.mark.parametrize("font_size", [20, 32])
def test_separate_names_keep_text_column_stable(width, position, font_size):
    options = ChatOverlayStyleOptions(
        name_mode="separate", animation="none", position=position, font_size=font_size,
    )
    template = Environment(loader=FileSystemLoader(ROOT / "app/templates")).get_template("chat_overlay.html")
    html = template.render(
        channel=SimpleNamespace(channel_name="Layout Test"),
        setting=SimpleNamespace(custom_css=build_overlay_css(options)),
        overlay_message_ttl_ms=60000,
        overlay_name_color_mode="fixed",
        overlay_name_color_palette="#ffffff",
        overlay_websocket_path="/ws",
    )
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": 720})
        page.set_content(html)
        page.evaluate("window.connectOverlaySocket = () => {}")
        page.add_script_tag(path=ROOT / "app/static/js/chat_overlay.js")
        page.evaluate("addMessage({nickname: 'A', message: 'hello'})")
        measure = """() => {
            const text = document.querySelector('.chat-text').getBoundingClientRect();
            const frame = document.querySelector('.chat-frame').getBoundingClientRect();
            return {x: text.x, width: text.width, frameX: frame.x, frameWidth: frame.width};
        }"""
        initial = page.evaluate(measure)
        page.evaluate("""addMessage({nickname: '가나다라마바', message: 'hello', badges: [
            'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20"/>',
            'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20"/>',
            'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20"/>'
        ]})""")
        page.locator('.chat-badge').evaluate_all("images => Promise.all(images.map(image => image.decode()))")
        assert page.evaluate(measure) == initial
        assert page.locator('.chat-name').last.evaluate("""e => {
            const range = document.createRange();
            range.selectNodeContents(e.querySelector('.chat-nickname'));
            const badges = e.querySelector('.chat-badges').getBoundingClientRect();
            const nickname = e.querySelector('.chat-nickname').getBoundingClientRect();
            return range.getClientRects().length === 1 && e.scrollWidth <= e.clientWidth
                && nickname.top < badges.bottom && badges.top < nickname.bottom;
        }""")
        # 배지가 공간을 차지하면 닉네임 전체를 다음 줄로 옮깁니다.
        page.add_style_tag(content=".chat-list { grid-template-columns: 7em minmax(0, 1fr); }")
        assert page.locator('.chat-name').last.evaluate("""e => {
            const badges = e.querySelector('.chat-badges').getBoundingClientRect();
            const nickname = e.querySelector('.chat-nickname');
            const range = document.createRange();
            range.selectNodeContents(nickname);
            return nickname.getBoundingClientRect().top >= badges.bottom
                && range.getClientRects().length === 1;
        }""")
        page.add_style_tag(content=".chat-list { grid-template-columns: 10em minmax(0, 1fr); }")
        page.evaluate("addMessage({nickname: 'LongNickname'.repeat(8), message: 'hello'})")
        assert page.evaluate(measure) == initial
        assert page.locator('.chat-name').last.evaluate("e => e.scrollWidth <= e.clientWidth")
        assert page.locator('.chat-nickname').last.evaluate("""e => {
            const range = document.createRange();
            range.selectNodeContents(e);
            return range.getClientRects().length > 1;
        }""")
        page.locator('.chat-message').last.evaluate("e => e.remove()")
        assert page.evaluate(measure) == initial
        browser.close()
