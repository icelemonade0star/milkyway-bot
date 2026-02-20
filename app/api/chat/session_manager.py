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
