import asyncio
import inspect
import json
import logging
import random

import httpx
import websockets

from app.features.chat_overlay.broadcaster import chat_overlay_broadcaster

logger = logging.getLogger("ChzzkRawClient")

_LIVE_DETAIL_URL = "https://api.chzzk.naver.com/service/v3/channels/{channel_id}/live-detail"
_WS_SERVERS = [f"wss://kr-ss{n}.chat.naver.com/chat" for n in range(1, 7)]
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
_CHATID_RETRY_DELAY = 30
_RECONNECT_DELAY = 5

# 실제 수집 확인된 채팅 cmd
_CHAT_CMDS = {93101}

# websockets 버전별 헤더 파라미터 분기 (11.x: extra_headers, 15/16.x: additional_headers)
_CONNECT_PARAMS = inspect.signature(websockets.connect).parameters


def _ws_connect_kwargs() -> dict:
    if "additional_headers" in _CONNECT_PARAMS:
        return {
            "additional_headers": {},
            "origin": "https://chzzk.naver.com",
            "user_agent_header": _USER_AGENT,
        }
    return {
        "extra_headers": {
            "Origin": "https://chzzk.naver.com",
            "User-Agent": _USER_AGENT,
        }
    }


_WS_CONNECT_KWARGS = _ws_connect_kwargs()


class ChzzkRawChatClient:
    def __init__(self, platform_channel_id: str):
        self.platform_channel_id = platform_channel_id
        self._http = httpx.AsyncClient(
            timeout=10.0,
            headers={
                "User-Agent": _USER_AGENT,
                "Origin": "https://chzzk.naver.com",
                "Referer": f"https://chzzk.naver.com/live/{platform_channel_id}",
            },
        )

    async def _get_chat_channel_id(self) -> str | None:
        url = _LIVE_DETAIL_URL.format(channel_id=self.platform_channel_id)
        try:
            resp = await self._http.get(url)
            if resp.status_code == 200:
                content = resp.json().get("content") or {}
                return content.get("chatChannelId") or None
        except Exception as e:
            logger.warning("[%s] live-detail 조회 실패: %s", self.platform_channel_id, e)
        return None

    async def run_forever(self):
        while True:
            try:
                chat_channel_id = await self._get_chat_channel_id()
                if not chat_channel_id:
                    logger.info("[%s] chatChannelId 없음. %ds 후 재시도", self.platform_channel_id, _CHATID_RETRY_DELAY)
                    await asyncio.sleep(_CHATID_RETRY_DELAY)
                    continue

                ws_url = random.choice(_WS_SERVERS)
                logger.info("[%s] 연결 시도: %s", self.platform_channel_id, ws_url)

                async with websockets.connect(ws_url, ping_interval=None, **_WS_CONNECT_KWARGS) as ws:
                    auth_packet = json.dumps({
                        "bdy": {
                            "accTkn": "",
                            "auth": "READ",
                            "devType": 2001,
                            "uid": None,
                        },
                        "cmd": 100,
                        "cid": chat_channel_id,
                        "svcid": "game",
                        "tid": 1,
                        "ver": "2",
                    })
                    await ws.send(auth_packet)
                    logger.info("[%s] 인증 패킷 전송 완료", self.platform_channel_id)

                    async for raw_msg in ws:
                        if isinstance(raw_msg, bytes):
                            raw_msg = raw_msg.decode("utf-8", errors="ignore")
                        await self._handle_message(ws, raw_msg, chat_channel_id)

            except asyncio.CancelledError:
                logger.info("[%s] raw WS 태스크 취소됨", self.platform_channel_id)
                await self._http.aclose()
                raise
            except Exception as e:
                logger.warning("[%s] raw WS 오류: %s. %ds 후 재연결", self.platform_channel_id, e, _RECONNECT_DELAY)
                await asyncio.sleep(_RECONNECT_DELAY)

    async def _handle_message(self, ws, raw_msg: str, chat_channel_id: str):
        try:
            data = json.loads(raw_msg)
        except (json.JSONDecodeError, TypeError):
            return

        cmd = data.get("cmd")

        if cmd == 0:
            pong = json.dumps({
                "bdy": {},
                "cmd": 10000,
                "svcid": "game",
                "cid": chat_channel_id,
                "tid": data.get("tid", 2),
                "ver": data.get("ver", "2"),
            })
            await ws.send(pong)

        elif cmd in _CHAT_CMDS:
            bdy = data.get("bdy", [])
            if isinstance(bdy, dict):
                bdy = [bdy]
            for body in bdy:
                if isinstance(body, dict):
                    await self._process_chat(body)

    async def _process_chat(self, body: dict):
        profile = body.get("profile", {})
        if isinstance(profile, str):
            try:
                profile = json.loads(profile)
            except (json.JSONDecodeError, TypeError):
                profile = {}

        extras = body.get("extras", {})
        if isinstance(extras, str):
            try:
                extras = json.loads(extras)
            except (json.JSONDecodeError, TypeError):
                extras = {}

        message = body.get("msg") or body.get("content") or ""
        if not message:
            return

        nickname = (
            profile.get("nickname")
            or profile.get("nick")
            or profile.get("name")
            or body.get("nickname")
            or ""
        )
        user_id = profile.get("userIdHash") or profile.get("userId") or body.get("uid") or ""
        role = profile.get("userRoleCode") or body.get("userRoleCode") or ""
        emojis = extras.get("emojis", {}) if isinstance(extras, dict) else {}

        # streamingProperty.nicknameColor.colorCode → "#RRGGBB" 정규화
        streaming_prop = profile.get("streamingProperty") or {}
        raw_color = (streaming_prop.get("nicknameColor") or {}).get("colorCode") or ""
        nickname_color = f"#{raw_color}" if raw_color and not raw_color.startswith("#") else raw_color

        badge = profile.get("badge") or {}
        badge_url = badge.get("imageUrl") if isinstance(badge, dict) else ""

        payload = {
            "nickname": nickname,
            "message": message,
            "role": role,
            "user_id": user_id,
            "extras": extras,
            "emojis": emojis,
            "nickname_color": nickname_color,
            "badge_url": badge_url,
            "raw": body,
        }

        await chat_overlay_broadcaster.publish(self.platform_channel_id, payload)
