from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

import app.core.config as config
from app.platforms.base import LiveStatus


_OPENAPI_HEADERS = {
    "Client-Id": config.CLIENT_ID,
    "Client-Secret": config.CLIENT_SECRET,
    "Content-Type": "application/json",
}
_OPENAPI_CLIENT = httpx.AsyncClient(
    base_url=config.OPENAPI_BASE,
    headers=_OPENAPI_HEADERS,
    timeout=10.0,
)
_PUBLIC_CLIENT = httpx.AsyncClient(timeout=5.0)


class ChzzkLiveProvider:
    platform = "chzzk"

    async def close(self):
        return None

    async def get_channel_info(self, platform_channel_id: str) -> dict[str, Any] | None:
        response = await _OPENAPI_CLIENT.get(
            "/open/v1/channels",
            params={"channelIds": platform_channel_id},
        )
        if response.status_code != 200:
            return None

        content = response.json().get("content", {})
        data = content.get("data") or []
        return data[0] if data else {}

    async def get_live_status(self, platform_channel_id: str) -> LiveStatus | None:
        url = f"https://api.chzzk.naver.com/polling/v3.1/channels/{platform_channel_id}/live-status"
        response = await _PUBLIC_CLIENT.get(url)
        if response.status_code != 200:
            return None

        content = response.json().get("content") or {}
        status = content.get("status") or "UNKNOWN"
        opened_at = self._parse_kst_datetime(content.get("openDate"))
        closed_at = self._parse_kst_datetime(content.get("closeDate"))

        return LiveStatus(
            platform=self.platform,
            platform_channel_id=platform_channel_id,
            status=status,
            opened_at=opened_at,
            closed_at=closed_at,
            title=content.get("liveTitle"),
            category=content.get("liveCategoryValue") or content.get("liveCategory"),
            thumbnail_url=content.get("liveImageUrl"),
            raw=content,
        )

    def get_live_url(self, platform_channel_id: str) -> str:
        return f"https://chzzk.naver.com/live/{platform_channel_id}"

    @staticmethod
    def _parse_kst_datetime(value: str | None) -> datetime | None:
        if not value:
            return None
        kst = timezone(timedelta(hours=9))
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=kst)
