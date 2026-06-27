# 🌌 Milkyway Bot (밀키웨이 봇)

**Milkyway Bot**은 치지직(Chzzk) 스트리밍 플랫폼을 위한 고성능 비동기 챗봇입니다.  
FastAPI와 SQLAlchemy(Async)를 기반으로 구축되었으며, 확장 가능한 구조를 통해 다양한 플랫폼 지원을 목표로 하고 있습니다.

## 📝 업데이트 내역 (Update Log)

- **2026.02.23**: v1.0.0 오픈
- **2026.02.24**: v1.1.0 인사말 및 기본 출석 기능 추가
- **2026.03.11**: v1.2.0 디스코드 봇 추가 (치지직 방송 알림 연동)
- **2026.03.31**: v1.3.0 출석 시스템 고도화 (방송 세션 기반, 연속/누적 출석)
- **2026.04.26**: v1.4.0 인사말 Redis 캐시 안정성 개선 및 채널당 등록 한도 추가
- **2026.05.21**: v1.5.0 스트리머 대시보드 추가 (치지직 OAuth 로그인, 명령어/인사말 조회 및 수정, 명령어 쿨타임/활성 상태 관리)
- **2026.06.11**: v1.6.0 대시보드 출석 명령어 추가, 출석/인사말 치환자 확장, 출석 명령어 시청자별 쿨타임 적용
- **2026.06.24**: v1.7.0 채팅 오버레이 편집기 추가 (OBS 링크, 미리보기, 테스트 채팅 전송, 옵션 기반 스타일링, 프리셋 저장/불러오기, 고급 CSS 스킨)

## ✨ 주요 기능

- **치지직 연동**: OAuth 인증, 실시간 채팅 수신 및 전송
- **비동기 처리**: `asyncio`와 `FastAPI`를 활용한 Non-blocking I/O
- **출석 체크**: 방송 세션 기반의 출석, 연속 출석, 총 출석 횟수 관리
- **명령어 시스템**:
  - 전역 명령어 (Global Commands)
  - 채널별 커스텀 명령어 (Custom Commands)
- **출석 명령어 커스터마이징**: 대시보드에서 채널별 출석 명령어와 출석/중복출석/방송 중 아님 응답 문구 관리
- **인사말 기능**: 특정 키워드에 반응하는 자동 응답 메시지
- **응답 치환자**: `[닉네임]`, `[출석일]`, `[연속출석일]` 치환 지원
- **스트리머 대시보드**: 치지직 OAuth 로그인 기반으로 채널 명령어, 인사말, 출석 랭킹, 디스코드 알림 상태 확인
- **대시보드 관리 기능**: 명령어/인사말 추가, 수정, 삭제 및 명령어 쿨타임/활성 상태 변경
- **채팅 오버레이**: OBS 브라우저 소스용 채팅창 링크 제공, 샘플/현재 채팅 미리보기, 옵션 기반 디자인 편집
- **오버레이 프리셋과 스킨**: 스타일 프리셋 저장/불러오기, 고급 CSS 편집, 이미지 스킨 적용을 위한 `.chat-frame`, `.chat-list`, `.chat-message` 구조 지원
- **데이터베이스**: PostgreSQL (SQLAlchemy ORM 사용)
- **디스코드 연동**: 치지직 방송 시작 시 실시간 채널 알림
- **보안**: SSH 터널링을 통한 안전한 DB 연결 지원, 관리자 API 토큰 인증

## 🛠️ 기술 스택

- **Language**: Python 3.13+
- **Web Framework**: FastAPI
- **Database**: PostgreSQL, SQLAlchemy (Async)
- **Socket**: python-socketio, aiohttp
- **Infra/Tools**: Paramiko (SSH Tunneling), Uvicorn, Discord.py

## 📄 개발 환경 및 인코딩

- 소스 코드, 문서, 템플릿은 모두 **UTF-8** 기준으로 관리합니다.
- Windows PowerShell에서 한글이 깨져 보이면 터미널 코드 페이지를 UTF-8로 변경한 뒤 다시 확인하세요.

```powershell
chcp 65001
```

- 저장 시 에디터 인코딩은 `UTF-8`, 줄바꿈은 `LF`를 사용합니다. 기본 설정은 `.editorconfig`와 `.gitattributes`에 정의되어 있습니다.

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
pip install -r requirements.txt
```

### 3. 환경 변수 설정 (.env)

프로젝트 루트에 `.env` 파일을 생성하고 아래 내용을 채워주세요.

```ini
# Docker Config
DOCKERHUB_USERNAME=your_dockerhub_username

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
PUBLIC_SITE_URL=https://milkywaybot.cloud
# 로컬 HTTP 테스트 시 false, 운영 HTTPS 환경에서는 true 권장
DASHBOARD_COOKIE_SECURE=true

# Chat Bot Config
# 봇 자신의 닉네임이나 다른 봇의 닉네임을 입력해 무한 응답 루프를 방지합니다. (쉼표로 구분)
BOT_NICKNAMES=밀키웨이 봇, 다른 봇닉네임
CHAT_DELAY=0.5
# 채널당 최대 명령어 등록 개수 (기본값: 100)
MAX_COMMANDS_PER_CHANNEL=100
# 명령어 이름 최대 글자 수 (기본값: 100)
MAX_COMMAND_NAME_CHARS=100
# 구분자(|)로 나눈 각 응답 항목의 최대 글자 수 (기본값: 100)
MAX_CHAT_RESPONSE_CHARS=100
# 채널당 최대 인사말 등록 개수 (기본값: 30)
MAX_GREETINGS_PER_CHANNEL=30

# Discord Config
DISCORD_TOKEN=your_discord_bot_token

# Admin API Token
# /admin/*, /chat/send, /chat/create/session, /chat/close/session, /auth/list, /auth/refresh 보호
ADMIN_TOKEN=your_secure_admin_token_here

```

### 4. API 보안 (Admin Token)

관리자 전용 엔드포인트는 `X-Admin-Token` 헤더로 보호됩니다.

**보호 대상 엔드포인트:**

- `GET /admin/*` — 전체 관리자 API
- `GET /chat/send`
- `GET /chat/create/session`, `/chat/create/session/force`, `/chat/close/session`
- `GET /auth/list`
- `POST /auth/refresh/{channel_id}`

**대시보드 로그인:**

- `/auth/dashboard` 접속
- `/auth/dashboard/login`에서 치지직 OAuth 인증
- 치지직 redirect URI는 기존 `/auth/callback` 하나만 사용
- callback에서 등록된 채널 여부 확인 후 대시보드 세션 발급

**대시보드에서 가능한 작업:**

- 채널 명령어 목록 조회
- 채널 명령어 추가, 응답 수정, 삭제
- 명령어별 쿨타임 초 단위 변경 및 활성 상태 토글
- 출석 명령어 1개 등록 및 출석/중복출석/방송 중 아님 응답 문구 수정
- 출석 명령어 쿨타임은 채널 전체가 아닌 시청자별로 적용
- 인사말 목록 조회
- 인사말 추가, 응답 수정, 삭제
- 출석 랭킹 및 디스코드 알림 설정 상태 확인
- 채팅 오버레이 고정 OBS 링크 확인 및 복사
- 채팅 오버레이 샘플/실시간 미리보기 및 테스트 채팅 직접 전송
- 채팅 오버레이 글자 크기, 폭, 여백, 말풍선, 색상, 애니메이션, 유지시간 설정
- 시청자 닉네임 고정 색상 또는 랜덤 팔레트 설정
- 닉네임 기준 차단 및 스트리머/관리자 역할 기준 필터링
- 오버레이 스타일 프리셋 저장, 적용, 삭제
- 고급 CSS 모드로 이미지 스킨과 세부 스타일 직접 편집

**채팅 오버레이 사용 흐름:**

1. 대시보드의 채팅 오버레이 화면에서 닉네임과 메시지를 직접 입력해 테스트 채팅을 보내며 디자인을 확인합니다.
2. 옵션을 조정한 뒤 **적용**을 눌러 저장합니다.
3. 필요한 경우 프리셋으로 저장해 다른 스타일을 빠르게 불러옵니다.
4. 복사한 오버레이 링크를 OBS 브라우저 소스 URL에 넣습니다.
5. 오버레이 링크는 고정 주소라 OBS에 한 번 등록하면 계속 사용할 수 있습니다.

**채팅 오버레이 CSS 스킨 기준:**

- `.chat-overlay`: 오버레이 전체 배치와 크기 기준
- `.chat-frame`: 채팅창 프레임, 배경 이미지, 외곽 장식
- `.chat-list`: 메시지 영역의 여백, 정렬, 클리핑
- `.chat-message`: 개별 말풍선, 말풍선 이미지, 입장 애니메이션
- `.chat-name`: 닉네임 표시 영역
- `.chat-text`: 채팅 본문 영역

스킨이 없어도 기본 CSS만으로 동작하며, 고급 CSS 모드는 CSS를 아는 사용자가 이미지 프레임이나 말풍선 이미지를 얹는 용도로 사용할 수 있습니다.

**응답 치환자:**

- `[닉네임]`: 채팅을 입력한 시청자 닉네임
- `[출석일]`: 해당 시청자의 총 출석 횟수
- `[연속출석일]`: 해당 시청자의 연속 출석 횟수
- 일반 명령어는 `[닉네임]` 치환을 지원합니다.
- 출석 명령어와 인사말은 `[닉네임]`, `[출석일]`, `[연속출석일]` 치환을 지원합니다.

**출석 명령어 주의사항:**

- 대시보드에서 추가하는 출석 명령어는 채널마다 1개만 등록할 수 있습니다.
- 출석 명령어의 쿨타임은 시청자별로 적용되므로, 여러 시청자가 동시에 사용할 수 있습니다.
- 방송 시작 직후 많은 시청자가 출석 명령어를 사용하면 출석 응답이 채팅에 많이 표시될 수 있습니다.
- 기본 `!출석` 응답과 인사말 응답은 채널 단위 쿨타임 흐름을 따릅니다.

**Swagger UI에서 인증하기:**

1. `/api/swagger` 접속
2. 우측 상단 **Authorize** 버튼 클릭
3. `X-Admin-Token` 필드에 `.env`의 `ADMIN_TOKEN` 값 입력

**직접 호출 시:**

```bash
curl -H "X-Admin-Token: your_token" https://milkywaybot.cloud/auth/list
```

### 5. 서버 실행

```bash
# 개발 모드 실행 (코드 변경 시 자동 재시작)
uvicorn app.main:app --reload
```
