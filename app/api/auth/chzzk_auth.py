import httpx
import app.config as config
import secrets
import asyncio

from urllib.parse import quote

from app.api.auth.auth_service import AuthService
 
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
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(self.chzzk_token_url, headers=headers, json=data)
                
                if response.status_code == 200:
                    res_json = response.json()
                    self.access_token = res_json["content"]["accessToken"]
                    self.refresh_token = res_json["content"]["refreshToken"]
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
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(self.chzzk_user_info_url, headers=headers)
                
                if response.status_code == 200:
                    res_json = response.json()
                    self.channel_id = res_json["content"]["channelId"]
                    self.channel_name = res_json["content"]["channelName"]
                    return res_json
                return f"Error: {response.status_code} - {response.text}"
                
            except Exception as e:
                return f"Error: {str(e)}"
        
    async def refresh_access_token(self, channel_id: str):
        # 1. DB에서 기존 리프레시 토큰 가져오기
        auth_data = await self.auth_service.get_auth_token_by_id(channel_id)
        print(f"[DEBUG] DB에서 가져온 데이터: {auth_data}")
        if not auth_data or not auth_data.refresh_token:
            print(f"❌ 갱신 불가: {channel_id}의 리프레시 토큰이 없습니다.")
            return None

        # 2. 치지직 토큰 갱신 API 호출
        data = {
            "grantType": "refresh_token",
            "clientId": self.client_id,
            "clientSecret": self.client_secret,
            "refreshToken": auth_data.refresh_token
        }

        print(f"[DEBUG] 전송 페이로드: RT={auth_data.refresh_token[:10]}..., ID={self.client_id[:5]}...")

        async with httpx.AsyncClient() as client:
            resp = await client.post(self.chzzk_token_url, json=data)
            if resp.status_code == 200:
                res_json = resp.json()
                token = await self.auth_service.update_auth_token(channel_id, res_json["content"])
                return token
            else:
                print(f"❌ 토큰 갱신 실패: {resp.status_code} - {resp.text}")
                return None
    



if __name__ == "__main__":
    async def test_main():
        print("chzzk_auth.py 테스트 시작")
        auth = ChzzkAuth()
        
        # 1. URL 생성 (동기 함수이므로 그대로 호출)
        url, state = auth.get_auth_url()
        print("client_id 정보 : ", auth.client_id)
        print("생성된 URL : ", url)
        
        # 2. 토큰 발급 테스트 (실제 code와 state가 있어야 하지만 구조 체크용)
        result = await auth.get_access_token("SAMPLE_CODE", state)
        print("토큰 결과 : ", result)

    # 비동기 루프 실행
    asyncio.run(test_main())