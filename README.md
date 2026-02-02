# YunPalWildarrows
Palworld server project for Streamer EunHaYun

    

1. 가상 환경 생성

```bash
py -3.13 -m venv .venv

2. 가상 환경 활성화
.venv\Scripts\activate

3. fastapi 설치
pip install fastapi uvicorn

4. FastAPI 서버 실행 (예시)
uvicorn app.main:app --reload
uvicorn app.api.auth.auth:app --reload


Socket.IO 서버 및 클라이언트
pip install websocket-client
pip install python-socketio==4.6.1

db 연결도구
pip install psycopg2-binary
pip install sqlalchemy psycopg2-binary


단독 파일 실행 예시
python -m app.tests.api_test.~파일명~
python -m app.chzzk.auth.chzzk_auth
python -m app.api.auth.auth



pip install python-dotenv
pip install paramiko==2.12.0