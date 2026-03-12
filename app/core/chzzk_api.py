import httpx
from typing import Optional, Dict, Any
import app.core.config as config
from app.core.logger import get_logger

logger = get_logger("ChzzkAPI")

class ChzzkAPIClient:
    def __init__(self):
        self.client_id = config.CLIENT_ID
        self.client_secret = config.CLIENT_SECRET
        self.openapi_base = config.OPENAPI_BASE
        
        # 공통 헤더 설정
        self.headers = {
            'Client-Id': self.client_id,
            'Client-Secret': self.client_secret,
            'Content-Type': 'application/json',
        }

        # 비동기 클라이언트 생성 (연결 재사용)
        self.client = httpx.AsyncClient(
            base_url=self.openapi_base, 
            headers=self.headers, 
            timeout=10.0
        )

    async def close(self):
        """클라이언트 리소스 정리"""
        await self.client.aclose()

    async def get_channel_info(self, channel_id: str) -> Optional[Dict[str, Any]]:
        url = '/open/v1/channels'
        params = {"channelIds": channel_id}
        
        try:
            response = await self.client.get(url, params=params)
            
            if response.status_code == 200:
                data = response.json()
                # content -> data 배열의 첫 번째 요소 반환
                content = data.get('content', {})
                if content and 'data' in content and len(content['data']) > 0:
                    return content['data'][0]
                return {}
            else:
                logger.error(f"❌ 채널 정보 조회 실패: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            logger.error(f"⚠️ 채널 정보 요청 중 에러: {e}")
            return None