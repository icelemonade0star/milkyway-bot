import httpx
import app.core.config as config
import secrets
import asyncio
from datetime import datetime, timedelta

# 모듈 레벨 클라이언트 — 매 호출마다 TCP 연결 재생성 방지
_http_client = httpx.AsyncClient(timeout=10.0)

from urllib.parse import quote

from app.features.auth.service import AuthService
 
class ChzzkAuth:
    def __init__(self, auth_service: AuthService):
        self.client_id = config.CLIENT_ID
        self.client_secret = config.CLIENT_SECRET
        self.redirect_url = config.REDIRECT_URL
        self.auth_service = auth_service
        
        # 치지직 토큰관련 엔드포인트 URL 정의
        self.chzzk_auth_url = "https://chzzk.naver.com/account-interlock"
        self.chzzk_token_url = config.OPENAPI_BASE + "/auth/v1/token"
        self.chzzk_user_info_url = config.OPENAPI_BASE + "/open/v1/users/me"

        self.state = secrets.token_urlsafe(16)  # 보안을 위한 랜덤 문자열 생성

        # 인증 정보 저장
        self.channel_id = None
        self.channel_name = None
        self.access_token = None
        self.refresh_token = None
        self.expires_at = None

    def get_auth_url(self):
        state = secrets.token_urlsafe(16)
        # redirect_url을 URL 인코딩
        encoded_redirect = quote(self.redirect_url)
        
        # 사용자 인증을 위한 URL 생성
        auth_url = (
            f"{self.chzzk_auth_url}"
            f"?response_type=code"
            f"&clientId={self.client_id}"
            f"&redirectUri={encoded_redirect}"
            f"&state={state}"
        )
        return auth_url, state
        
    async def get_access_token(self, code, state):
        headers = {          
            'Content-Type': 'application/json'
        }
        
        data = {
            "grantType": "authorization_code",  
            "clientId": self.client_id,
            "clientSecret": self.client_secret,
            "code": code,                       
            "state": state,                     
            "redirectUri": self.redirect_url        
        }
        
        try:
            response = await _http_client.post(self.chzzk_token_url, headers=headers, json=data)

            if response.status_code == 200:
                res_json = response.json()
                self.access_token = res_json["content"]["accessToken"]
                self.refresh_token = res_json["content"]["refreshToken"]

                # 만료 시간 계산 및 저장 (기본값 1일)
                expires_in = res_json["content"].get("expiresIn", 86400)
                self.expires_at = datetime.now() + timedelta(seconds=expires_in)
                return res_json
            return None
        except Exception as e:
            print(f"Token Error: {str(e)}")
            return None

    async def get_user_info(self):
        headers = {          
            'Content-Type': 'application/json',
            "Authorization": f"Bearer {self.access_token}"
        }
        
        try:
            response = await _http_client.get(self.chzzk_user_info_url, headers=headers)

            if response.status_code == 200:
                res_json = response.json()
                self.channel_id = res_json["content"]["channelId"]
                self.channel_name = res_json["content"]["channelName"]
                return res_json
            return f"Error: {response.status_code} - {response.text}"

        except Exception as e:
            return f"Error: {str(e)}"
        
    async def refresh_access_token(self, channel_id: str):
        """(new_access_token, failure_status_code) 튜플 반환.
        성공: (token, None) / API 오류: (None, status_code) / 네트워크 오류: (None, None)
        """
        # 1. DB에서 기존 리프레시 토큰 가져오기
        auth_data = await self.auth_service.get_auth_token_by_id(channel_id)
        if not auth_data or not auth_data.refresh_token:
            print(f"❌ 갱신 불가: {channel_id}의 리프레시 토큰이 없습니다.")
            return None, None

        # 2. 치지직 토큰 갱신 API 호출
        data = {
            "grantType": "refresh_token",
            "clientId": self.client_id,
            "clientSecret": self.client_secret,
            "refreshToken": auth_data.refresh_token
        }

        try:
            resp = await _http_client.post(self.chzzk_token_url, json=data)
        except Exception as e:
            print(f"❌ 토큰 갱신 네트워크 오류: {str(e)}")
            return None, None

        if resp.status_code == 200:
            res_json = resp.json()
            token = await self.auth_service.update_auth_token(channel_id, res_json["content"])
            return token, None
        else:
            print(f"❌ 토큰 갱신 실패: {resp.status_code} - {resp.text}")
            return None, resp.status_code