from app.chzzk.auth.chzzk_auth import ChzzkAuth

from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.query_loader import query_loader

app = FastAPI()


# 인증 객체 생성
auth = ChzzkAuth()

@app.get("/auth")
def get_auth():
    # 리다이렉트
    return RedirectResponse(url=auth.get_auth_url())

@app.get("/auth/callback")
def callback_auth(
    code: str, 
    state: str, 
    db: Session = Depends(get_db)
):
    
    if not auth.is_valid_state(state):
        raise HTTPException(status_code=400, detail="Invalid state")

    auth.get_access_token(code)
    auth.get_user_info()

    print("채널이름 : ",auth.channel_name)
    print("채널 ID : ",auth.channel_id)
    print("액세스 토큰 : ",auth.access_token)

    # db저장
    insert_query = query_loader.get_query(
        "auth_token_insert",
        channel_id=auth.channel_id,      # :channel_id
        channel_name=auth.channel_name,  # :channel_name  
        access_token=auth.access_token,  # :access_token
        refresh_token=auth.refresh_token # :refresh_token
    )

    result = db.execute(insert_query)
    db.commit()

    inserted_data = result.fetchone()
    print(f"✅ DB 저장 완료! ID: {inserted_data.id}")
    
    return {
        "message": "인증 성공 & DB 저장 완료",
        "채널 이름": inserted_data.channel_name,
        "만료일": inserted_data.expires_at
    }

# 예외처리. 따로 분리할것
@app.post("/authenticate")
def authenticate():
    raise HTTPException(status_code=401, detail="Unauthorized")