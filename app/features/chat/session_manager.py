import asyncio
import logging
from app.platforms.chzzk.chat import ChzzkSessions
from app.platforms.constants import PLATFORM_CHZZK

SESSION_PLATFORM = PLATFORM_CHZZK

logger = logging.getLogger("SessionManager")

class SessionManager:
    def __init__(self):
        self.active_sessions = {}  # {channel_id: platform chat session instance}
        # 동시 생성 방지를 위한 락 (channel_id별로 관리)
        self._locks = {}

    def add_session(self, channel_id, session):
        self.active_sessions[channel_id] = session


    async def restore_all_sessions_from_db(self, db_session):
        """
        서버 시작 시 DB에서 인증 정보를 가진 모든 채널을 불러와 연결을 복구합니다.
        """
        from app.features.auth.service import AuthService 
        auth_service = AuthService(db_session)
        channels = await auth_service.get_auth_list(SESSION_PLATFORM)

        # 동시에 너무 많은 세션을 복구하면 API Rate Limit(429)이 발생할 수 있으므로 Semaphore 제한 추가
        semaphore = asyncio.Semaphore(10) # 한 번에 최대 10개씩 연결
        
        async def _bounded_restore(channel_id):
            async with semaphore:
                return await self.get_or_create_session(channel_id)

        tasks = []
        for ch in channels:
            tasks.append(_bounded_restore(ch.channel_id))
        
        # 병렬로 모든 세션 복구 시작
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for i, res in enumerate(results):
                if isinstance(res, Exception):
                    # 어떤 채널(ID)에서 에러가 났는지 로그에 남김
                    logger.error(f"❌ 세션 복구 실패: {res}")
            logger.info(f"✅ {len(results)}개의 세션 복구 시도 완료")

    def get_existing_session(self, channel_id: str):
        """이미 생성된 세션만 반환합니다. 없으면 None."""
        return self.active_sessions.get(channel_id)

    async def get_or_create_session(self, channel_id: str, force_recreate: bool = False):
        """
        세션을 반환합니다. 없으면 새로 생성하고 초기화(연결)까지 마칩니다.
        """
        # 해당 채널용 락이 없으면 생성
        if channel_id not in self._locks:
            self._locks[channel_id] = asyncio.Lock()

        # 락을 사용하여 중복 생성 방지 (Critical Section)
        async with self._locks[channel_id]:
            existing_session = self.active_sessions.get(channel_id)
            if existing_session and not force_recreate:
                return existing_session, False

            logger.info(f"🆕 [{channel_id}] 새 세션 생성 및 초기화 시작")

            # 현재 채팅 세션 구현체는 기본 플랫폼(chzzk)을 사용한다.
            new_session = ChzzkSessions(channel_id)

            # 2. 실제 플랫폼 서버와 연결 및 구독 (비동기 작업)
            # 새 세션이 완전히 준비되기 전까지는 기존 세션을 건드리지 않는다.
            # (force_recreate로 기존 세션이 있던 경우) 여기서 실패하면 기존 세션이
            # active_sessions에 그대로 남아있으므로, 워치독이 다음 주기에 다시 감지해 재시도한다.
            # 단, 채널이 원래 active_sessions에 없던 최초 생성 실패의 경우는 워치독이
            # active_sessions만 순회하기 때문에 대상에 안 잡히고, 자동 재시도되지 않는다.
            try:
                await new_session.create_session()

                if not new_session.socket_url:
                    raise Exception("소켓 URL을 가져오지 못했습니다.")

                if not new_session.session_key:
                    raise Exception("세션 키를 받지 못했습니다. (소켓 연결 타임아웃)")

                subscribed = await new_session.subscribe_chat()
                if not subscribed:
                    raise Exception("채팅 구독에 실패했습니다.")
            except Exception:
                # 생성 도중 실패한 새 세션의 소켓이 열려있으면 정리(연결 누수 방지)
                # 정리 자체가 실패해도 원래 예외가 가려지지 않도록 별도로 삼킨다
                if new_session.socket_client:
                    try:
                        await new_session.socket_client.disconnect()
                    except Exception as cleanup_error:
                        logger.warning(f"⚠️ [{channel_id}] 실패한 세션 정리 중 오류(무시): {cleanup_error}")
                raise

            # 새 세션을 먼저 등록해, 이후 기존 세션 종료가 실패하더라도
            # 채널이 active_sessions에서 사라지지 않도록 한다(워치독 추적 대상 유지).
            self.active_sessions[channel_id] = new_session

            # 기존 세션 종료는 별도로 시도하고, 실패해도 새 세션 등록은 되돌리지 않는다.
            if existing_session and existing_session.socket_client:
                logger.info(f"♻️ [{channel_id}] 기존 세션 종료")
                try:
                    await existing_session.socket_client.disconnect()
                except Exception as e:
                    logger.warning(f"⚠️ [{channel_id}] 기존 세션 종료 중 오류(무시하고 진행): {e}")

            return new_session, True

    async def _disconnect_session(self, channel_id: str):
        """락을 보유한 상태에서 호출하는 내부용 세션 제거. _locks는 건드리지 않음."""
        session = self.active_sessions.pop(channel_id, None)
        if session and session.socket_client:
            await session.socket_client.disconnect()

    async def remove_session(self, channel_id: str):
        """외부 호출용 세션 종료. 락 획득 후 세션을 제거."""
        if channel_id not in self._locks:
            self._locks[channel_id] = asyncio.Lock()
        async with self._locks[channel_id]:
            await self._disconnect_session(channel_id)

    async def close_all(self):
        """서버 종료 시 모든 세션 안전하게 닫기"""
        for session in self.active_sessions.values():
            if session.socket_client:
                await session.socket_client.disconnect()
        self.active_sessions.clear()

    async def update_session_token(self, channel_id: str, new_access_token: str):
        """실행 중인 세션의 액세스 토큰을 갱신합니다."""
        if channel_id in self.active_sessions:
            session = self.active_sessions[channel_id]
            session.access_token = new_access_token
            logger.info(f"🔄 [SessionManager] {channel_id}의 인메모리 토큰이 갱신되었습니다.")

session_manager = SessionManager()
