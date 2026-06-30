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


def extract_badges(profile: dict[str, Any]) -> tuple[list[tuple[str, str, str]], list[str]]:
    """profile에서 표시할 뱃지를 반환합니다.

    뱃지 순서:
      1. profile.badge            — 역할 뱃지 (스트리머·매니저), null이면 생략
      2. profile.viewerBadges[i]  — 실제 채팅창에 표시되는 뱃지 목록
                                    구조: { type, badge: { badgeId, scope, imageUrl } }

    Returns:
        badges: (label, badgeId, imageUrl) 목록
        notes:  디버깅용 메모 (imageUrl 없는 항목, 미확인 필드 등)
    """
    badges: list[tuple[str, str, str]] = []
    notes: list[str] = []

    # 1. 역할 뱃지 — 스트리머·매니저일 때만 non-null
    role_badge = profile.get("badge") or {}
    if isinstance(role_badge, dict) and role_badge.get("imageUrl"):
        badges.append(("badge", role_badge.get("badgeId", ""), role_badge["imageUrl"]))

    # 2. 구독 뱃지 — streamingProperty.subscription.badge.imageUrl
    streaming_prop = profile.get("streamingProperty") or {}
    subscription = streaming_prop.get("subscription") or {}
    sub_badge = subscription.get("badge") or {} if isinstance(subscription, dict) else {}
    if isinstance(sub_badge, dict) and sub_badge.get("imageUrl"):
        tier = subscription.get("tier", "")
        months = subscription.get("accumulativeMonth", "")
        badges.append((f"subscription (tier={tier} {months}mo)", "subscription", sub_badge["imageUrl"]))

    # 3. 시청자 표시 뱃지 — { type, badge: { badgeId, scope, imageUrl } }
    viewer_list = profile.get("viewerBadges") or []
    for i, vb in enumerate(viewer_list):
        if not isinstance(vb, dict):
            notes.append(f"viewerBadges[{i}] dict 아님: {type(vb)}")
            continue
        inner = vb.get("badge") or {}
        url = inner.get("imageUrl") if isinstance(inner, dict) else None
        badge_id = inner.get("badgeId", "") if isinstance(inner, dict) else ""
        vb_type = vb.get("type", "")
        if url:
            badges.append((f"viewerBadges[{i}/{len(viewer_list)}] type={vb_type}", badge_id, url))
        else:
            notes.append(f"viewerBadges[{i}/{len(viewer_list)}] imageUrl 없음 type={vb_type} inner_keys={list(inner.keys()) if isinstance(inner, dict) else inner}")

    # 미확인 streamingProperty 하위 키 감지 (새 뱃지 발견용)
    known_sp_keys = {"nicknameColor", "subscription", "activatedAchievementBadgeIds"}
    for key, val in streaming_prop.items():
        if key in known_sp_keys:
            continue
        if isinstance(val, dict) and val.get("imageUrl"):
            badges.append((f"streamingProperty.{key} [UNKNOWN]", "", val["imageUrl"]))
        elif val:
            notes.append(f"streamingProperty.{key} [UNKNOWN] raw={str(val)[:120]}")

    return badges, notes


KNOWN_PROFILE_KEYS = {
    "nickname", "nick", "name", "userIdHash", "userId",
    "userRoleCode", "badge", "streamingProperty",
    "profileImageUrl", "title", "verifiedMark",
    "activityBadges", "viewerBadges",
}


def print_chat(packet: dict[str, Any], dump_profile: bool = True) -> dict[str, Any] | None:
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

        badges, badge_notes = extract_badges(profile)
        unknown_profile_keys = [k for k in profile if k not in KNOWN_PROFILE_KEYS]

        print(f"[{now()}] CHAT [{nickname}] role={role} user={user_id}: {message}")
        for label, title, url in badges:
            title_str = f" ({title})" if title else ""
            print(f"[{now()}]   [{label}]{title_str} {url}")
        for note in badge_notes:
            print(f"[{now()}]   [badge-note] {note}")
        if emojis:
            print(f"[{now()}]   emojis={json.dumps(emojis, ensure_ascii=False)}")
        if extras:
            print(f"[{now()}]   extras keys={list(extras.keys())}")
        if unknown_profile_keys:
            print(f"[{now()}]   !! unknown profile keys={unknown_profile_keys}")
        if dump_profile:
            print(f"[{now()}]   profile={json.dumps(profile, ensure_ascii=False)}")

        result = {
            "nickname": nickname,
            "message": message,
            "role": role,
            "user_id": user_id,
            "extras": extras,
            "emojis": emojis,
            "badges": [{"label": lbl, "title": t, "url": url} for lbl, t, url in badges],
        }
    return result


async def connect_chat(
    chat_channel_id: str,
    access_token: str,
    ws_url: str | None,
    dump_raw: bool,
    dump_profile: bool,
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
                parsed = print_chat(packet, dump_profile=dump_profile)
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
    dump_profile: bool,
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

            await connect_chat(chat_channel_id, access_token, ws_url, dump_raw, dump_profile, save_file)

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
    parser.add_argument("--dump-profile", action=argparse.BooleanOptionalAction, default=True, help="Print full profile JSON. Use --no-dump-profile to disable.")
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
        await connect_chat(chat_channel_id, args.access_token, args.ws_url or None, args.dump_raw, args.dump_profile, save_file)
    else:
        await run_forever(
            channel_id=args.channel_id,
            access_token=args.access_token,
            forced_chat_channel_id=args.chat_channel_id,
            ws_url=args.ws_url or None,
            dump_raw=args.dump_raw,
            dump_profile=args.dump_profile,
            save_file=save_file,
            reconnect_delay=5,
            chatid_retry_delay=30,
        )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n[{now()}] stopped")
