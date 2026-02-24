from app.api.auth.chzzk_auth import ChzzkAuth

from fastapi import APIRouter, HTTPException, Depends, Query, Cookie, BackgroundTasks
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_async_db
from app.api.auth.auth_service import AuthService
from app.api.chat.session_manager import session_manager

auth_router = APIRouter(prefix="/auth", tags=["auth"])

# 인증 객체 생성
# auth = ChzzkAuth()

def get_chzzk_auth(db: AsyncSession = Depends(get_async_db)) -> ChzzkAuth:
    auth_service = AuthService(db)
    return ChzzkAuth(auth_service)


@auth_router.get("/")
async def auth_redirect(chzzk: ChzzkAuth = Depends(get_chzzk_auth)):
    url, state = chzzk.get_auth_url()

    response = RedirectResponse(url=url)
    # 쿠키에 state 저장 (유효기간 5분)
    response.set_cookie(key="oauth_state", value=state, httponly=True, max_age=300)

    return response


@auth_router.get("/callback", response_class=HTMLResponse)
async def callback_auth(
    code: str = Query(...),
    state: str = Query(...),
    background_tasks: BackgroundTasks,
    oauth_state: str = Cookie(None),
    db: AsyncSession = Depends(get_async_db),
):
    chzzk_auth = get_chzzk_auth(db)
   
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
    
    # [추가] 인증 완료 후 백그라운드에서 세션 생성 및 채팅 연결 시작
    background_tasks.add_task(session_manager.get_or_create_session, chzzk_auth.channel_id)
    
    channel_name = getattr(inserted_data, 'channel_name', chzzk_auth.channel_name)

    html_content = f"""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>인증 완료 - Milkyway Bot</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
                background-color: #f4f7f6;
                display: flex;
                justify_content: center;
                align-items: center;
                height: 100vh;
                margin: 0;
            }}
            .container {{
                background: white;
                padding: 40px;
                border-radius: 12px;
                box-shadow: 0 4px 15px rgba(0,0,0,0.1);
                text-align: center;
                max-width: 400px;
                width: 90%;
            }}
            h1 {{ color: #2c3e50; margin-bottom: 10px; }}
            p {{ color: #7f8c8d; margin-bottom: 30px; line-height: 1.5; }}
            .btn {{ background-color: #00c73c; color: white; border: none; padding: 12px 24px; border-radius: 6px; font-size: 16px; cursor: pointer; }}
            .btn:hover {{ background-color: #00b035; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>✨ 인증 성공!</h1>
            <p><strong>{channel_name}</strong>님, 환영합니다.<br>이제 봇이 정상적으로 연동되었습니다.</p>
            <button class="btn" onclick="window.close()">창 닫기</button>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


@auth_router.get("/list")
async def get_auth_token_list(
    channel_name: str = Query(None, description="검색할 채널 이름 (선택 사항)"),
    db: AsyncSession = Depends(get_async_db)
):
    auth_service = AuthService(db)
    rows = await auth_service.get_auth_list(channel_name)
    
    # 결과를 딕셔너리 리스트로 변환하여 반환
    return {
        "count": len(rows),
        "items": [
            {
                "channel_id": row.channel_id,
                "channel_name": row.channel_name,
                "expires_at": row.expires_at,
                "created_at": getattr(row, 'created_at', None)
            } for row in rows
        ]
    }

@auth_router.post("/refresh/{channel_id}")
async def refresh_token(
    channel_id: str, 
    chzzk_auth: ChzzkAuth = Depends(get_chzzk_auth)
):
    new_token = await chzzk_auth.refresh_access_token(channel_id)
    return {"status": "success", "token": new_token}

# 예외처리. 따로 분리할것
@auth_router.post("/authenticate")
async def authenticate():
    raise HTTPException(status_code=401, detail="Unauthorized")