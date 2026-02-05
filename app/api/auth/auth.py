from app.chzzk.auth.chzzk_auth import ChzzkAuth
from typing import Any

from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session


from app.db.database import get_db
from app.db.query_loader import query_loader

auth_router = APIRouter(prefix="/auth", tags=["auth"])

# 인증 객체 생성
# auth = ChzzkAuth()

def get_auth() -> ChzzkAuth:
    return ChzzkAuth()


@auth_router.get("/")
def auth_redirect():
    # 리다이렉트
    auth = get_auth()
    return RedirectResponse(url=auth.get_auth_url())


@auth_router.get("/callback")
def callback_auth(
    code: str = Query(...),
    state: str = Query(...),
    db: Session = Depends(get_db),
):
    chzzk_auth = get_auth()
   
    if not chzzk_auth.is_valid_state(state):
        raise HTTPException(status_code=400, detail="Invalid state")


    if not chzzk_auth.get_access_token(code, state):
        raise HTTPException(status_code=400, detail="토큰 발급 실패")
    
    if not chzzk_auth.get_user_info():
        raise HTTPException(status_code=400, detail="유저 정보 조회 실패")


    print("채널이름 : ",chzzk_auth.channel_name)
    print("채널 ID : ",chzzk_auth.channel_id)
    print("액세스 토큰 : ",chzzk_auth.access_token)


    # db저장
    insert_query = query_loader.get_query(
        "auth_token_insert",
        channel_id=chzzk_auth.channel_id,      # :channel_id
        channel_name=chzzk_auth.channel_name,  # :channel_name  
        access_token=chzzk_auth.access_token,  # :access_token
        refresh_token=chzzk_auth.refresh_token # :refresh_token
    )


    result = db.execute(insert_query)
    db.commit()


    if result.rowcount == 0:
        raise HTTPException(status_code=500, detail="DB 저장 실패")


    inserted_data = result.fetchone()
    print(f"✅ DB 저장 완료! ID: {inserted_data.id}")
   
    return {
        "message": "인증 성공 & DB 저장 완료",
        "채널 이름": inserted_data.channel_name,
        "만료일": inserted_data.expires_at
    }


# 예외처리. 따로 분리할것
@auth_router.post("/authenticate")
def authenticate():
    raise HTTPException(status_code=401, detail="Unauthorized")