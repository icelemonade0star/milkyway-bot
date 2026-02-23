import asyncio
from app.api.auth.auth_service import AuthService
from app.api.auth.chzzk_auth import ChzzkAuth
from app.api.chat.session_manager import session_manager

async def token_refresh_task(session_factory):
    """
    백그라운드에서 주기적으로 만료 임박 토큰을 검사하고 갱신합니다.
    """
    print("⏰ 토큰 자동 갱신 작업이 시작되었습니다.")
    
    while True:
        try:
            async with session_factory() as db:
                auth_service = AuthService(db)
                chzzk_auth = ChzzkAuth(auth_service)
                
                # 1. 만료 13시간(780분) 전인 토큰들 조회 (다음 검사가 12시간 뒤이므로 여유 있게 설정)
                expiring_tokens = await auth_service.get_expiring_tokens(limit_minutes=780)
                
                if expiring_tokens:
                    print(f"🔍 갱신 대상 토큰 발견: {len(expiring_tokens)}개")
                
                for token in expiring_tokens:
                    try:
                        print(f"🔄 [{token.channel_name}] 토큰 갱신 시도 중...")
                        
                        # 2. 토큰 갱신 요청 (DB 업데이트 포함됨)
                        new_access_token = await chzzk_auth.refresh_access_token(token.channel_id)
                        
                        if new_access_token:
                            # 3. 현재 활성화된 세션이 있다면 메모리 상의 토큰도 업데이트
                            await session_manager.update_session_token(token.channel_id, new_access_token)
                            print(f"✅ [{token.channel_name}] 토큰 갱신 완료")
                        else:
                            print(f"❌ [{token.channel_name}] 토큰 갱신 실패")
                            
                    except Exception as e:
                        print(f"⚠️ [{token.channel_name}] 갱신 중 에러 발생: {e}")

        except Exception as e:
            print(f"⚠️ 토큰 갱신 작업 루프 에러: {e}")
        
        # 12시간마다 검사 (43200초)
        await asyncio.sleep(43200)