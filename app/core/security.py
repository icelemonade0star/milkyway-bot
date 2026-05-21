import base64
import hashlib
import hmac
import json
import secrets
import time

from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader

import app.core.config as config

api_key_header = APIKeyHeader(name="X-Admin-Token", auto_error=False)
DASHBOARD_SESSION_COOKIE = "dashboard_session"
DASHBOARD_SESSION_TTL_SECONDS = 60 * 60 * 24
OAUTH_STATE_TTL_SECONDS = 60 * 5
OAUTH_STATE_PURPOSE_DASHBOARD = "dashboard"


def _dashboard_secret() -> str:
    secret = config.ADMIN_TOKEN or config.CLIENT_SECRET
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="대시보드 세션 서명 키가 설정되지 않았습니다.",
        )
    return secret


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _b64decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def create_dashboard_session_token(channel_id: str, channel_name: str | None = None) -> str:
    payload = {
        "channel_id": channel_id,
        "channel_name": channel_name,
        "exp": int(time.time()) + DASHBOARD_SESSION_TTL_SECONDS,
    }
    payload_part = _b64encode(json.dumps(payload, separators=(",", ":")).encode())
    signature = hmac.new(
        _dashboard_secret().encode(),
        payload_part.encode(),
        hashlib.sha256,
    ).digest()
    return f"{payload_part}.{_b64encode(signature)}"


def verify_dashboard_session_token(token: str | None) -> dict:
    if not token or "." not in token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="대시보드 로그인이 필요합니다.")

    payload_part, signature_part = token.split(".", 1)
    expected_signature = hmac.new(
        _dashboard_secret().encode(),
        payload_part.encode(),
        hashlib.sha256,
    ).digest()

    try:
        provided_signature = _b64decode(signature_part)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="대시보드 세션이 올바르지 않습니다.")

    if not hmac.compare_digest(expected_signature, provided_signature):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="대시보드 세션이 올바르지 않습니다.")

    try:
        payload = json.loads(_b64decode(payload_part))
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="대시보드 세션을 읽을 수 없습니다.")

    if int(payload.get("exp", 0)) < int(time.time()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="대시보드 세션이 만료되었습니다.")

    return payload


def create_oauth_state_token(purpose: str) -> str:
    payload = {
        "purpose": purpose,
        "nonce": secrets.token_urlsafe(16),
        "exp": int(time.time()) + OAUTH_STATE_TTL_SECONDS,
    }
    payload_part = _b64encode(json.dumps(payload, separators=(",", ":")).encode())
    signature = hmac.new(
        _dashboard_secret().encode(),
        payload_part.encode(),
        hashlib.sha256,
    ).digest()
    return f"{payload_part}.{_b64encode(signature)}"


def verify_oauth_state_token(token: str) -> dict | None:
    if not token or "." not in token:
        return None

    payload_part, signature_part = token.split(".", 1)
    expected_signature = hmac.new(
        _dashboard_secret().encode(),
        payload_part.encode(),
        hashlib.sha256,
    ).digest()

    try:
        provided_signature = _b64decode(signature_part)
    except Exception:
        return None

    if not hmac.compare_digest(expected_signature, provided_signature):
        return None

    try:
        payload = json.loads(_b64decode(payload_part))
    except Exception:
        return None

    if int(payload.get("exp", 0)) < int(time.time()):
        return None

    return payload


async def verify_admin_token(api_key: str = Security(api_key_header)):
    if not config.ADMIN_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="서버에 ADMIN_TOKEN이 설정되지 않았습니다.",
        )
    if api_key != config.ADMIN_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 관리자 토큰입니다.",
            headers={"WWW-Authenticate": "X-Admin-Token"},
        )
