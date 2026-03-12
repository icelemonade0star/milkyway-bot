import asyncio
import logging
from app.features.chat.chzzk_sessions import ChzzkSessions

logger = logging.getLogger("SessionManager")

class SessionManager:
    def __init__(self):
        self.active_sessions = {}  # {channel_id: ChzzkSessions 인스턴스}

    def add_session(self, channel_id, session):
        self.active_sessions[channel_id] = session


    async def restore_all_sessions_from_db(self, db_session):
        """
        서버 시작 시 DB에서 인증 정보를 가진 모든 채널을 불러와 연결을 복구합니다.
        """
        from app.features.auth.service import AuthService 
        auth_service = AuthService(db_session)
        channels = await auth_service.get_auth_list()

        tasks = []
        for ch in channels:
            tasks.append(self.get_or_create_session(ch.channel_id))
        
        # 병렬로 모든 세션 복구 시작
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for i, res in enumerate(results):
                if isinstance(res, Exception):
                    # 어떤 채널(ID)에서 에러가 났는지 로그에 남김
                    logger.error(f"❌ 세션 복구 실패: {res}")
            logger.info(f"✅ {len(results)}개의 세션 복구 시도 완료")

    async def get_session(self, channel_id: str):
        """세션이 있으면 반환하고, 없으면 생성해서 반환합니다."""
        session, _ = await self.get_or_create_session(channel_id)
        return session
    
    async def get_or_create_session(self, channel_id: str, force_recreate: bool = False):
        """
        세션을 반환합니다. 없으면 새로 생성하고 초기화(연결)까지 마칩니다.
        """
        if channel_id in self.active_sessions:
            if not force_recreate:
                return self.active_sessions[channel_id], False
            
            logger.info(f"♻️ [{channel_id}] 기존 세션 강제 종료 및 재생성")
            await self.remove_session(channel_id)

        logger.info(f"🆕 [{channel_id}] 새 세션 생성 및 초기화 시작")
        
        new_session = ChzzkSessions(channel_id)
        
        # 2. 실제 치지직 서버와 연결 및 구독 (비동기 작업)
        await new_session.create_session()
        
        if not new_session.socket_url:
            raise Exception("소켓 URL을 가져오지 못했습니다.")

        await new_session.subscribe_chat()
        
        self.active_sessions[channel_id] = new_session
        return new_session, True

    async def remove_session(self, channel_id: str):
        """특정 채널 세션 종료 및 제거"""
        session = self.active_sessions.pop(channel_id, None)
        if session:
            if session.socket_client:
                await session.socket_client.disconnect()
            await session.client.aclose() # httpx 클라이언트 닫기

    async def close_all(self):
        """서버 종료 시 모든 세션 안전하게 닫기"""
        for session in self.active_sessions.values():
            if session.socket_client:
                await session.socket_client.disconnect()
            await session.client.aclose()
        self.active_sessions.clear()

    async def update_session_token(self, channel_id: str, new_access_token: str):
        """실행 중인 세션의 액세스 토큰을 갱신합니다."""
        if channel_id in self.active_sessions:
            session = self.active_sessions[channel_id]
            session.access_token = new_access_token
            logger.info(f"🔄 [SessionManager] {channel_id}의 인메모리 토큰이 갱신되었습니다.")

session_manager = SessionManager()