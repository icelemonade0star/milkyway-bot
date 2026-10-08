import logging
from urllib.parse import quote, urlsplit

import httpx

logger = logging.getLogger(__name__)


async def get_live_background_url(platform_channel_id: str) -> str | None:
    channel_id = quote(platform_channel_id, safe="")
    url = f"https://api.chzzk.naver.com/service/v3/channels/{channel_id}/live-detail"
    try:
        async with httpx.AsyncClient(timeout=5.0, headers={
            "User-Agent": "Mozilla/5.0",
            "Origin": "https://chzzk.naver.com",
            "Referer": f"https://chzzk.naver.com/live/{channel_id}",
        }) as client:
            response = await client.get(url)
            response.raise_for_status()
            payload = response.json()
        if not isinstance(payload, dict):
            return None
        content = payload.get("content")
        if not isinstance(content, dict):
            return None
        image_url = content.get("liveImageUrl")
        if not isinstance(image_url, str) or not image_url.strip():
            return None
        image_url = image_url.strip().replace("{type}", "720")
        parsed = urlsplit(image_url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            return None
        return image_url
    except (httpx.HTTPError, ValueError) as error:
        logger.warning("[%s] 그림 배경용 방송 이미지 조회 실패: %s", platform_channel_id, error)
        return None
