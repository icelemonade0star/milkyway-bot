import requests
import httpx
import json
import asyncio

import app.config as config
import app.api.chat.handling.chat_client as chat_client
from app.api.auth.auth_service import AuthService

class ChzzkSessions:
    def __init__(self, channel_id: str, auth_service: AuthService):
        self.client_id = config.CLIENT_ID
        self.client_secret = config.CLIENT_SECRET
        self.openapi_base = config.OPENAPI_BASE

        self.auth_service = auth_service
        self.channel_id = channel_id
        self.channel_name = None
        self.access_token = None
        self.socket_url = None
        self.session_key = None

    async def _ensure_auth(self):
        if not self.access_token:
            auth_data = await self.auth_service.get_auth_token_by_id(self.channel_id)
            if auth_data:
                self.access_token = auth_data.access_token
                self.channel_name = auth_data.channel_name
            else:
                raise Exception(f"토큰을 찾을 수 없습니다: {self.channel_id}")

    async def create_socket_url(self):
        # 세션 발급을 위한 치지직 API 주소
        url = f'{self.openapi_base}/open/v1/sessions/auth/client'

        # 토큰 확인
        # await self._ensure_auth()
        
        # 내 앱의 ID랑 비밀키로 인증 헤더 구성
        headers = {
            'Client-Id': f'{self.client_id}',
            'Client-Secret': f'{self.client_secret}',
            # 'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        }
        
        # 서버에 세션 생성 url 요청
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)
        
        if response.status_code == 200:
            print("url 정상", response.json())
            data = response.json()
            
            # 응답 데이터에서 실제 소켓 서버 주소만 추출
            socket_url = data.get('content', {}).get('url')
            self.socket_url = socket_url
        else:
            # 실패하면 에러 코드 찍고 끝냄
            print(f"Error: {response.status_code} - {response.text}")
            self.socket_url = None
        
    async def create_session(self):

        # 소켓 URL이 없으면 새로 생성
        if not self.socket_url:
            await self.create_socket_url()

        if not self.socket_url: return

        chatClient = chat_client.ChzzkChatClient(self.channel_name)

        # 소켓 연결
        await chatClient.connect(self.socket_url)
        
        # 세션 키 대기 (Timeout 5초로 확장 및 로그 구체화)
        timeout = 5.0
        start_time = asyncio.get_event_loop().time()
        
        while asyncio.get_event_loop().time() - start_time < timeout:
            current_key = chatClient.get_session_key()
            if current_key:
                self.session_key = current_key
                print(f"✨ 세션 키 확인 완료: {current_key}")
                return current_key
            await asyncio.sleep(0.2)
        
        print("⚠️ 세션 키 확인 실패: 타임아웃")
        return None
    
    async def subscribe_chat(self):

        # 토큰 확인
        await self._ensure_auth()
        
        # 인증 토큰이랑 데이터 형식을 헤더에 담기
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        }

        if not self.session_key:
            print("⚠️ 구독 실패: 세션 키가 없습니다.")
            return False
        
        # 서버에 보낼 파라미터(소켓 세션 키) 설정
        params = {
            "sessionKey": self.session_key
        }
        uri = f"{self.openapi_base}/open/v1/sessions/events/subscribe/chat"

        async with httpx.AsyncClient() as client:
            response = await client.post(uri, headers=headers, params=params)
        
        # 요청 성공(200 OK)이면 결과값을 JSON으로 돌려줌
        if response.status_code == 200:
            return response.json() 
        # 실패하면 에러 코드랑 메시지 반환
        else:
            return {
                "error": "API request failed", 
                "status_code": response.status_code,
                "detail": response.json() if response.text else "No detail"
            }
    
    async def send_chat(self, message: str):

        # 토큰 확인
        await self._ensure_auth()
        
        # 인증 토큰이랑 데이터 형식을 헤더에 담기
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json', 
        }

        # 메시지 데이터 구성
        data = {
            "message": message
        }

        uri = f"{config.OPENAPI_BASE}/open/v1/chats/send"

        async with httpx.AsyncClient() as client:
            response = await client.post(uri, headers=headers, json=data)
        
        if response.status_code == 200:
            print(f"✅ 채팅 전송 성공: {message}")
            return True
        else:
            print(f"❌ 채팅 전송 실패: {response.status_code} - {response.text}")
            return False