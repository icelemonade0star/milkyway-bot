from app.api.auth.chzzk_auth import ChzzkAuth

from fastapi import APIRouter, HTTPException, Depends, Query, Cookie
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.db.database import get_async_db
from app.db.query_loader import query_loader
from app.api.auth.auth_service import AuthService

auth_router = APIRouter(prefix="/auth", tags=["auth"])

# 인증 객체 생성
# auth = ChzzkAuth()

def get_auth() -> ChzzkAuth:
    return ChzzkAuth()


@auth_router.get("/")
async def auth_redirect():
    # 리다이렉트
    auth = get_auth()
    url, state = auth.get_auth_url()

    response = RedirectResponse(url=url)
    # 쿠키에 state 저장 (유효기간 5분)
    response.set_cookie(key="oauth_state", value=state, httponly=True, max_age=300)

    return response


@auth_router.get("/callback")
async def callback_auth(
    code: str = Query(...),
    state: str = Query(...),
    oauth_state: str = Cookie(None),
    db: AsyncSession = Depends(get_async_db),
):
    chzzk_auth = get_auth()
   
    # 쿠키에 저장된 state와 네이버가 보낸 state 비교
    if not oauth_state or state != oauth_state:
        raise HTTPException(status_code=400, detail="Invalid state")

    if not await chzzk_auth.get_access_token(code, state):
        raise HTTPException(status_code=400, detail="토큰 발급 실패")
    
    if not await chzzk_auth.get_user_info():
        raise HTTPException(status_code=400, detail="유저 정보 조회 실패")


    print("채널이름 : ",chzzk_auth.channel_name)
    print("채널 ID : ",chzzk_auth.channel_id)
    print("액세스 토큰 : ",chzzk_auth.access_token)

    auth_service = AuthService(db)
    inserted_data = await auth_service.save_chzzk_auth(chzzk_auth)
        
    if not inserted_data:
            return {"message": "인증 성공 & DB 저장 완료 (반환값 없음)"}

    return {
        "message": "인증 성공 & DB 저장 완료",
        "채널 이름": getattr(inserted_data, 'channel_name', chzzk_auth.channel_name),
        "만료일": getattr(inserted_data, 'expires_at', 'N/A')
    }


# 예외처리. 따로 분리할것
@auth_router.post("/authenticate")
async def authenticate():
    raise HTTPException(status_code=401, detail="Unauthorized")