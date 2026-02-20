from app.api.chat.chzzk_sessions import ChzzkSessions

class SessionManager:
    def __init__(self):
        self.active_sessions = {}  # {channel_id: ChzzkSessions 인스턴스}

    def add_session(self, channel_id, session):
        self.active_sessions[channel_id] = session

    async def get_session(self, channel_id: str) -> ChzzkSessions:
        """세션이 있으면 반환하고, 없으면 생성해서 반환합니다."""
        if channel_id not in self.active_sessions:
            print(f"🆕 [{channel_id}] 새 세션 생성 및 캐싱")
            # ChzzkSessions 생성
            session = ChzzkSessions(channel_id)
            self.active_sessions[channel_id] = session
            
        return self.active_sessions[channel_id]
    
    async def get_or_create_session(self, channel_id: str) -> tuple[ChzzkSessions, bool]:
        """
        세션을 반환합니다. 없으면 새로 생성하고 초기화(연결)까지 마칩니다.
        반환값: (세션 객체, 신규 생성 여부)
        """
        if channel_id in self.active_sessions:
            return self.active_sessions[channel_id], False

        print(f"🆕 [{channel_id}] 새 세션 생성 및 초기화 시작")
        
        # 1. 인스턴스 생성
        new_session = ChzzkSessions(channel_id)
        
        # 2. 실제 치지직 서버와 연결 및 구독 (비동기 작업)
        await new_session.create_session()
        
        if not new_session.socket_url:
            raise Exception("소켓 URL을 가져오지 못했습니다.")

        await new_session.subscribe_chat()
        
        # 3. 매니저에 등록
        self.active_sessions[channel_id] = new_session
        return new_session, True

    async def remove_session(self, channel_id: str):
        """특정 채널 세션 종료 및 제거"""
        session = self.active_sessions.pop(channel_id, None)
        if session:
            await session.client.aclose() # httpx 클라이언트 닫기

    async def close_all(self):
        """서버 종료 시 모든 세션 안전하게 닫기"""
        for session in self.active_sessions.values():
            await session.client.aclose()
        self.active_sessions.clear()

session_manager = SessionManager()
