import httpx
import asyncio
from datetime import datetime

import app.config as config
import app.api.chat.clients.chat_client as chat_client
from app.api.auth.auth_service import AuthService
from app.db.database import get_session_factory

class ChzzkSessions:
    def __init__(self, channel_id: str):
        self.client_id = config.CLIENT_ID
        self.client_secret = config.CLIENT_SECRET
        self.openapi_base = config.OPENAPI_BASE

        self.channel_id = channel_id
        self.channel_name = None
        self.access_token = None
        self.socket_url = None
        self.session_key = None
        self.socket_client = None # 소켓 클라이언트 인스턴스 저장

        # HTTP 클라이언트를 하나로 유지
        self.client = httpx.AsyncClient(timeout=10.0)

    async def _ensure_auth(self, force_refresh=False):

        # 이미 토큰이 있고, 강제 갱신이 아니면 패스
        if self.access_token and not force_refresh:
            return
        

        factory = get_session_factory()
        if not factory:
            raise Exception("DB 세션 팩토리가 초기화되지 않았습니다.")

        async with factory() as db:
            auth_service = AuthService(db)
            auth_data = await auth_service.get_auth_token_by_id(self.channel_id)

            if auth_data:
                # 만료 시간 확인 (DB에 저장된 시간)
                # 백그라운드 태스크(13시간)보다 조금 더 여유 있게 14시간(50400초) 전이면 미리 갱신
                expires_at = auth_data.expires_at
                now = datetime.now(expires_at.tzinfo) if expires_at.tzinfo else datetime.now()
                
                if (expires_at - now).total_seconds() < 50400:
                    print(f"⚠️ [{self.channel_id}] 토큰 만료 임박(14시간 이내). 선제적 갱신 시도...")
                    from app.api.auth.chzzk_auth import ChzzkAuth
                    chzzk_auth = ChzzkAuth(auth_service)
                    new_token = await chzzk_auth.refresh_access_token(self.channel_id)
                    if new_token:
                        auth_data.access_token = new_token
                        print(f"✅ [{self.channel_id}] 선제적 토큰 갱신 완료")

                self.access_token = auth_data.access_token
                self.channel_name = auth_data.channel_name
                print(f"🔑 [{self.channel_id}] 인증 정보 로드 완료")
            else:
                raise Exception(f"토큰을 찾을 수 없습니다: {self.channel_id}")

    async def _refresh_token(self):
        """401 에러 발생 시 토큰을 갱신하고 메모리에 반영합니다."""
        print(f"🔄 [{self.channel_id}] API 401 응답 감지. 토큰 갱신 시도...")
        
        # 순환 참조 방지를 위해 함수 내부에서 import
        from app.api.auth.chzzk_auth import ChzzkAuth
        
        factory = get_session_factory()
        if not factory:
            print("⚠️ DB 세션 팩토리가 없습니다.")
            return False

        async with factory() as db:
            auth_service = AuthService(db)
            chzzk_auth = ChzzkAuth(auth_service)
            
            new_token = await chzzk_auth.refresh_access_token(self.channel_id)
            
            if new_token:
                self.access_token = new_token
                print(f"✅ [{self.channel_id}] 토큰 갱신 및 메모리 업데이트 완료")
                return True
            else:
                print(f"❌ [{self.channel_id}] 토큰 갱신 실패")
                return False

    async def create_socket_url(self):
        # 세션 발급을 위한 치지직 API 주소
        url = f'{self.openapi_base}/open/v1/sessions/auth/client'

        # 내 앱의 ID랑 비밀키로 인증 헤더 구성
        headers = {
            'Client-Id': f'{self.client_id}',
            'Client-Secret': f'{self.client_secret}',
            'Content-Type': 'application/json'
        }
        
        # 서버에 세션 생성 url 요청
        response = await self.client.get(url, headers=headers)
        
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

        # 채널 이름 등 정보를 얻기 위해 인증 정보 확인 (소켓 연결 전 필수)
        await self._ensure_auth()

        # 소켓 URL이 없으면 새로 생성
        if not self.socket_url:
            await self.create_socket_url()

        if not self.socket_url: return

        # 세션 키 수신을 대기할 Future 객체 생성
        session_key_future = asyncio.Future()
        
        # 클라이언트에 Future 전달
        self.socket_client = chat_client.ChzzkChatClient(self.channel_name, session_key_future)

        # 소켓 연결
        await self.socket_client.connect(self.socket_url)
        
        try:
            # Future가 완료될 때까지 최대 5초 대기 (Polling 제거)
            self.session_key = await asyncio.wait_for(session_key_future, timeout=5.0)
            print(f"✨ 세션 키 확인 완료: {self.session_key}")
            return self.session_key
        except asyncio.TimeoutError:
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

        response = await self.client.post(uri, headers=headers, params=params)

        # 401 Unauthorized 발생 시 토큰 갱신 후 재시도
        if response.status_code == 401:
            if await self._refresh_token():
                headers['Authorization'] = f'Bearer {self.access_token}'
                response = await self.client.post(uri, headers=headers, params=params)
        
        # 요청 성공(200 OK)이면 결과값을 JSON으로 돌려줌
        if response.status_code == 200:
            print(f"✅ [{self.channel_id}] 채팅 구독 성공")
            return response.json() 
        # 실패하면 에러 코드랑 메시지 반환
        else:
            print(f"❌ [{self.channel_id}] 채팅 구독 실패: {response.status_code} - {response.text}")
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

        uri = f"{self.openapi_base}/open/v1/chats/send"

        # 채팅창 순서 꼬임 방지를 위한 전송 딜레이
        if config.CHAT_DELAY > 0:
            await asyncio.sleep(config.CHAT_DELAY)

        response = await self.client.post(uri, headers=headers, json=data)

        # 401 Unauthorized 발생 시 토큰 갱신 후 재시도
        if response.status_code == 401:
            if await self._refresh_token():
                headers['Authorization'] = f'Bearer {self.access_token}'
                response = await self.client.post(uri, headers=headers, json=data)
        
        if response.status_code == 200:
            print(f"✅ 채팅 전송 성공: {message}")
            return True
        else:
            print(f"❌ 채팅 전송 실패: {response.status_code} - {response.text}")
            return False