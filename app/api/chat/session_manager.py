class SessionManager:
    def __init__(self):
        self.active_sessions = {}  # {channel_id: ChzzkSessions 인스턴스}

    def add_session(self, channel_id, session):
        self.active_sessions[channel_id] = session

    def get_session(self, channel_id):
        return self.active_sessions.get(channel_id)

    async def close_all(self):
        for session in self.active_sessions.values():
            await session.disconnect() # disconnect 메서드 구현 필요

session_manager = SessionManager()
