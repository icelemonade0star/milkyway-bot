# 🌌 Milkyway Bot (밀키웨이 봇)

**Milkyway Bot**은 치지직(Chzzk) 스트리밍 플랫폼을 위한 고성능 비동기 챗봇입니다.  
FastAPI와 SQLAlchemy(Async)를 기반으로 구축되었으며, 확장 가능한 구조를 통해 다양한 플랫폼 지원을 목표로 하고 있습니다.

## 📝 업데이트 내역 (Update Log)

- **2026.02.23**: v1.0.0 오픈
- **2026.02.24**: v1.1.0 인삿말 관련 명령어 추가 (인사등록, 변경, 삭제 등) 출석 로직 및 명령어 추가

## ✨ 주요 기능

- **치지직 연동**: OAuth 인증, 실시간 채팅 수신 및 전송
- **비동기 처리**: `asyncio`와 `FastAPI`를 활용한 Non-blocking I/O
- **명령어 시스템**:
  - 전역 명령어 (Global Commands)
  - 채널별 커스텀 명령어 (Custom Commands)
- **데이터베이스**: PostgreSQL (SQLAlchemy ORM 사용)
- **보안**: SSH 터널링을 통한 안전한 DB 연결 지원

## 🛠️ 기술 스택

- **Language**: Python 3.13+
- **Web Framework**: FastAPI
- **Database**: PostgreSQL, SQLAlchemy (Async)
- **Socket**: python-socketio, aiohttp
- **Infra/Tools**: Paramiko (SSH Tunneling), Uvicorn

## 🚀 설치 및 실행 가이드

### 1. 프로젝트 클론 및 가상환경 설정

```bash
# 가상환경 생성 (Python 3.13 권장)
py -3.13 -m venv .venv

# 가상환경 활성화 (Windows)
.venv\Scripts\activate
```

### 2. 의존성 패키지 설치

```bash
pip install fastapi uvicorn[standard]
pip install sqlalchemy asyncpg
pip install python-socketio aiohttp
pip install python-dotenv
pip install paramiko
pip install requests httpx
```

### 3. 환경 변수 설정 (.env)

프로젝트 루트에 `.env` 파일을 생성하고 아래 내용을 채워주세요.

```ini
# Database Config
DB_USER=your_db_user
DB_PASSWORD=your_db_password
DB_HOST=your_db_host
DB_PORT=5432
DB_NAME=your_db_name

# SSH Tunnel Config (Optional)
SSH_HOST=ssh_host_address
SSH_PORT=22
SSH_USER=ssh_username
SSH_PASSWORD=ssh_password

# Chzzk API Config
CLIENT_ID=your_chzzk_client_id
CLIENT_SECRET=your_chzzk_client_secret
OPENAPI_BASE=https://openapi.chzzk.naver.com
```

### 4. 서버 실행

```bash
# 개발 모드 실행 (코드 변경 시 자동 재시작)
uvicorn app.main:app --reload
