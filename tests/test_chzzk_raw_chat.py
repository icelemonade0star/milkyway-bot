import argparse
import asyncio
import inspect
import json
import random
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import websockets


LIVE_DETAIL_URL = "https://api.chzzk.naver.com/service/v3/channels/{channel_id}/live-detail"
WS_SERVERS = [f"wss://kr-ss{n}.chat.naver.com/chat" for n in range(1, 7)]
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
CONNECT_PARAMETERS = inspect.signature(websockets.connect).parameters

# 실제 수집 확인된 채팅 cmd
CHAT_CMDS = {93101}


def now() -> str:
    return datetime.now().strftime("%H:%M:%S")


def parse_json_field(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def websocket_header_kwargs() -> dict[str, Any]:
    if "additional_headers" in CONNECT_PARAMETERS:
        return {
            "additional_headers": {},
            "origin": "https://chzzk.naver.com",
            "user_agent_header": USER_AGENT,
        }
    return {
        "extra_headers": {
            "Origin": "https://chzzk.naver.com",
            "User-Agent": USER_AGENT,
        },
    }


async def get_live_detail(channel_id: str) -> dict[str, Any] | None:
    headers = {
        "User-Agent": USER_AGENT,
        "Origin": "https://chzzk.naver.com",
        "Referer": f"https://chzzk.naver.com/live/{channel_id}",
    }
    async with httpx.AsyncClient(timeout=10.0, headers=headers) as client:
        response = await client.get(LIVE_DETAIL_URL.format(channel_id=channel_id))
        print(f"[{now()}] live-detail status={response.status_code}")
        if response.status_code != 200:
            print(response.text[:1000])
            return None

        data = response.json()
        content = data.get("content") or {}
        print(f"[{now()}] live status={content.get('status')} chatChannelId={content.get('chatChannelId')}")
        if not content.get("chatChannelId"):
            print(json.dumps(content, ensure_ascii=False, indent=2)[:3000])
        return content


async def send_auth(ws, chat_channel_id: str, access_token: str):
    packet = {
        "ver": "2",
        "cmd": 100,
        "svcid": "game",
        "cid": chat_channel_id,
        "bdy": {
            "uid": None,
            "devType": 2001,
            "accTkn": access_token,
            "auth": "READ",
        },
        "tid": 1,
    }
    await ws.send(json.dumps(packet, ensure_ascii=False))
    print(f"[{now()}] -> cmd=100 auth sent accTkn={'set' if access_token else 'empty'}")


async def send_pong(ws, packet: dict[str, Any], chat_channel_id: str):
    pong = {
        "ver": packet.get("ver", "2"),
        "cmd": 10000,
        "svcid": "game",
        "cid": chat_channel_id,
        "bdy": {},
        "tid": packet.get("tid", 2),
    }
    await ws.send(json.dumps(pong, ensure_ascii=False))
    print(f"[{now()}] -> cmd=10000 pong")


def iter_bodies(packet: dict[str, Any]) -> list[dict[str, Any]]:
    body = packet.get("bdy")
    if isinstance(body, dict):
        return [body]
    if isinstance(body, list):
        return [item for item in body if isinstance(item, dict)]
    return []


def print_chat(packet: dict[str, Any]) -> dict[str, Any] | None:
    result = None
    for body in iter_bodies(packet):
        profile = parse_json_field(body.get("profile"))
        extras = parse_json_field(body.get("extras"))

        message = body.get("msg") or body.get("content") or ""
        nickname = (
            profile.get("nickname")
            or profile.get("nick")
            or profile.get("name")
            or body.get("nickname")
            or "Unknown"
        )
        user_id = profile.get("userIdHash") or profile.get("userId") or body.get("uid") or ""
        role = profile.get("userRoleCode") or body.get("userRoleCode") or ""
        emojis = extras.get("emojis", {}) if isinstance(extras, dict) else {}

        streaming_prop = profile.get("streamingProperty") or {}
        raw_color = (streaming_prop.get("nicknameColor") or {}).get("colorCode") or ""
        nickname_color = f"#{raw_color}" if raw_color and not raw_color.startswith("#") else raw_color

        print(f"[{now()}] CHAT [{nickname}] role={role} color={nickname_color} user={user_id}: {message}")
        if emojis:
            print(f"[{now()}]   emojis={json.dumps(emojis, ensure_ascii=False)}")
        if extras:
            print(f"[{now()}]   extras keys={list(extras.keys())}")

        result = {
            "nickname": nickname,
            "message": message,
            "role": role,
            "user_id": user_id,
            "nickname_color": nickname_color,
            "extras": extras,
            "emojis": emojis,
        }
    return result


async def connect_chat(
    chat_channel_id: str,
    access_token: str,
    ws_url: str | None,
    dump_raw: bool,
    save_file: Path | None,
):
    target = ws_url or random.choice(WS_SERVERS)
    print(f"[{now()}] websocket connect {target}")
    async with websockets.connect(target, ping_interval=None, **websocket_header_kwargs()) as ws:
        print(f"[{now()}] websocket connected")
        await send_auth(ws, chat_channel_id, access_token)

        async for raw_message in ws:
            if isinstance(raw_message, bytes):
                raw_message = raw_message.decode("utf-8", errors="ignore")
            try:
                packet = json.loads(raw_message)
            except json.JSONDecodeError:
                print(f"[{now()}] non-json {raw_message[:300]}")
                continue

            cmd = packet.get("cmd")
            ret_code = packet.get("retCode")
            if dump_raw:
                print(json.dumps(packet, ensure_ascii=False, indent=2)[:5000])
            else:
                print(f"[{now()}] <- cmd={cmd} retCode={ret_code} keys={list(packet.keys())}")

            if cmd == 0:
                await send_pong(ws, packet, chat_channel_id)
            elif cmd in CHAT_CMDS:
                parsed = print_chat(packet)
                if save_file and parsed:
                    with save_file.open("a", encoding="utf-8") as f:
                        f.write(json.dumps(parsed, ensure_ascii=False) + "\n")
            elif ret_code not in (None, 0):
                print(f"[{now()}] error packet={json.dumps(packet, ensure_ascii=False)[:1000]}")


async def run_forever(
    channel_id: str,
    access_token: str,
    forced_chat_channel_id: str,
    ws_url: str | None,
    dump_raw: bool,
    save_file: Path | None,
    reconnect_delay: int = 5,
    chatid_retry_delay: int = 30,
):
    while True:
        try:
            chat_channel_id = forced_chat_channel_id
            if not chat_channel_id:
                detail = await get_live_detail(channel_id)
                if not detail:
                    print(f"[{now()}] live-detail 실패. {chatid_retry_delay}s 후 재시도")
                    await asyncio.sleep(chatid_retry_delay)
                    continue
                chat_channel_id = detail.get("chatChannelId") or ""

            if not chat_channel_id:
                print(f"[{now()}] chatChannelId 없음 (방송 중이 아님?). {chatid_retry_delay}s 후 재시도")
                await asyncio.sleep(chatid_retry_delay)
                continue

            await connect_chat(chat_channel_id, access_token, ws_url, dump_raw, save_file)

        except KeyboardInterrupt:
            raise
        except Exception as e:
            print(f"[{now()}] 오류: {e}. {reconnect_delay}s 후 재연결")
            await asyncio.sleep(reconnect_delay)


async def main():
    parser = argparse.ArgumentParser(description="Standalone Chzzk raw chat websocket probe.")
    parser.add_argument("channel_id", help="Chzzk platform channel id, not channel name.")
    parser.add_argument("--access-token", default="", help="Optional chat access token.")
    parser.add_argument("--chat-channel-id", default="", help="Skip live-detail and connect with this chatChannelId.")
    parser.add_argument("--ws-url", default="", help="Override websocket URL.")
    parser.add_argument("--dump-raw", action="store_true", help="Print full packets.")
    parser.add_argument("--save", default="", help="Append parsed chat lines to this file (JSONL).")
    parser.add_argument("--no-reconnect", action="store_true", help="Exit on disconnect instead of reconnecting.")
    args = parser.parse_args()

    save_file = Path(args.save) if args.save else None

    if args.no_reconnect:
        detail = await get_live_detail(args.channel_id)
        if not detail:
            return
        chat_channel_id = args.chat_channel_id or detail.get("chatChannelId") or ""
        if not chat_channel_id:
            print(f"[{now()}] chatChannelId is empty. Is the channel live?")
            return
        await connect_chat(chat_channel_id, args.access_token, args.ws_url or None, args.dump_raw, save_file)
    else:
        await run_forever(
            channel_id=args.channel_id,
            access_token=args.access_token,
            forced_chat_channel_id=args.chat_channel_id,
            ws_url=args.ws_url or None,
            dump_raw=args.dump_raw,
            save_file=save_file,
            reconnect_delay=5,
            chatid_retry_delay=30,
        )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n[{now()}] stopped")
