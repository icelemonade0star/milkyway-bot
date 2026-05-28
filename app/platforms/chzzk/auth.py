import secrets
from datetime import datetime, timedelta
from urllib.parse import quote

import httpx

import app.core.config as config
from app.features.auth.service import AuthService
from app.platforms.base import PlatformIdentity, TokenBundle

_http_client = httpx.AsyncClient(timeout=10.0)


class ChzzkAuthProvider:
    platform = "chzzk"

    def __init__(self, auth_service: AuthService):
        self.client_id = config.CLIENT_ID
        self.client_secret = config.CLIENT_SECRET
        self.redirect_url = config.REDIRECT_URL
        self.auth_service = auth_service

        self.chzzk_auth_url = "https://chzzk.naver.com/account-interlock"
        self.chzzk_token_url = config.OPENAPI_BASE + "/auth/v1/token"
        self.chzzk_user_info_url = config.OPENAPI_BASE + "/open/v1/users/me"

        self.state = secrets.token_urlsafe(16)
        self.channel_id = None
        self.channel_name = None
        self.access_token = None
        self.refresh_token = None
        self.expires_at = None
        self.raw_token_response = None

    def get_auth_url(self, state: str | None = None):
        state = state or secrets.token_urlsafe(16)
        encoded_redirect = quote(self.redirect_url)
        auth_url = (
            f"{self.chzzk_auth_url}"
            f"?response_type=code"
            f"&clientId={self.client_id}"
            f"&redirectUri={encoded_redirect}"
            f"&state={state}"
        )
        return auth_url, state

    async def exchange_code_for_token(self, code: str, state: str) -> TokenBundle | None:
        data = {
            "grantType": "authorization_code",
            "clientId": self.client_id,
            "clientSecret": self.client_secret,
            "code": code,
            "state": state,
            "redirectUri": self.redirect_url,
        }

        try:
            response = await _http_client.post(
                self.chzzk_token_url,
                headers={"Content-Type": "application/json"},
                json=data,
            )
        except Exception as e:
            print(f"Token Error: {str(e)}")
            return None

        if response.status_code != 200:
            return None

        res_json = response.json()
        content = res_json["content"]
        expires_in = content.get("expiresIn", 86400)

        self.access_token = content["accessToken"]
        self.refresh_token = content["refreshToken"]
        self.expires_at = datetime.now() + timedelta(seconds=expires_in)
        self.raw_token_response = res_json

        return TokenBundle(
            access_token=self.access_token,
            refresh_token=self.refresh_token,
            expires_at=self.expires_at,
            raw=res_json,
        )

    async def get_identity(self, access_token: str | None = None) -> PlatformIdentity | None:
        token = access_token or self.access_token
        if not token:
            return None

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }

        try:
            response = await _http_client.get(self.chzzk_user_info_url, headers=headers)
        except Exception as e:
            print(f"User info Error: {str(e)}")
            return None

        if response.status_code != 200:
            print(f"User info failed: {response.status_code} - {response.text}")
            return None

        res_json = response.json()
        content = res_json["content"]
        self.channel_id = content["channelId"]
        self.channel_name = content["channelName"]

        return PlatformIdentity(
            platform=self.platform,
            platform_channel_id=self.channel_id,
            channel_name=self.channel_name,
        )

    async def get_access_token(self, code, state):
        token = await self.exchange_code_for_token(code, state)
        return self.raw_token_response if token else None

    async def get_user_info(self):
        identity = await self.get_identity()
        if not identity:
            return None
        return {
            "content": {
                "channelId": identity.platform_channel_id,
                "channelName": identity.channel_name,
            }
        }

    async def refresh_access_token(self, channel_id: str):
        auth_data = await self.auth_service.get_auth_token_by_id(channel_id)
        if not auth_data or not auth_data.refresh_token:
            print(f"Token refresh unavailable: {channel_id} has no refresh token.")
            return None, None

        data = {
            "grantType": "refresh_token",
            "clientId": self.client_id,
            "clientSecret": self.client_secret,
            "refreshToken": auth_data.refresh_token,
        }

        try:
            resp = await _http_client.post(self.chzzk_token_url, json=data)
        except Exception as e:
            print(f"Token refresh network error: {str(e)}")
            return None, None

        if resp.status_code == 200:
            res_json = resp.json()
            token = await self.auth_service.update_auth_token(channel_id, res_json["content"])
            return token, None

        print(f"Token refresh failed: {resp.status_code} - {resp.text}")
        return None, resp.status_code


ChzzkAuth = ChzzkAuthProvider
