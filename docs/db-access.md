# 서버 DB 접속 방법

## 핵심 요약 (2026-07-11 기준, 이전 예정)

**운영 서버의 실제 PostgreSQL은 `docker-compose.yml`의 `db` 서비스가 아닙니다. 지금은요.**
호스트에 직접 설치된 PostgreSQL(`127.0.0.1:5432`, IPv4 전용)이 현재 진짜 운영 DB이고, **SSH 터널을 거쳐야만 접속**됩니다.

`docker-compose.yml`의 `db` 서비스(`postgres:13`, `milkywaybot-db-1`)는 과거 도커화를 시도했다가 실제 데이터 이전 없이 방치된 빈 컨테이너입니다(2026-07-11 기준 테이블 0개 확인). `docker compose exec db psql`로 확인하면 항상 잘못된(비어있는) 결과를 보게 되니 혼동하지 마세요.

**다만 이 구조 자체가 정상이 아닙니다.** 같은 서버 안에서 컨테이너가 자기 서버에 SSH로 재접속해 DB에 붙는 건 불필요한 우회이고, 오늘 겪은 접속 문제(IPv4/IPv6 해석 혼동, 터널 타임아웃 등)의 근본 원인입니다. **호스트 PostgreSQL을 `db` 서비스 컨테이너로 정식 이전하기로 결정**했습니다(기존 데이터 디렉토리를 그대로 컨테이너에 마운트하는 방식 검토 중, 데이터 덤프/복원 불필요할 가능성 있음 — 상세 계획은 실제 이전 작업 시 별도 기록). 이관이 완료되면 이 문서도 그에 맞게 다시 갱신해야 합니다. 이관 전까지는 아래 SSH 터널 경로가 유일한 접근 방법입니다.

## 왜 이렇게 되어 있는가

- `app/core/tunnel.py`의 `ParamikoTunnel`이 `.env`의 `SSH_HOST`가 설정돼 있으면 앱 기동 시 자동으로 SSH 터널을 엽니다.
  - SSH 접속 대상: `SSH_HOST:SSH_PORT`
  - 터널이 포워딩하는 목적지: `config.DB_HOST:config.DB_PORT`(SSH 서버, 즉 이 서버 자신의 관점에서 본 주소)
- `app/core/database.py`의 `create_db_engine(local_port)`이 이 터널의 로컬 포트로 접속합니다.
- `app/lifespan.py`가 앱 기동 시 이 흐름(`ParamikoTunnel()` → `create_db_engine(tunnel.local_port)`)을 그대로 사용합니다.
- 즉 운영 서버 안에서도 "자기 자신에게 SSH로 다시 접속해서, 그 세션을 통해 로컬 postgres로 포워딩"하는 방식으로 DB에 붙습니다. 로컬 개발 PC에서 원격 DB에 접근하려고 만든 경로를 서버 자신도 그대로 재사용하는 구조입니다.

## 함정: `localhost` vs `127.0.0.1`

서버의 PostgreSQL은 `127.0.0.1`(IPv4)에만 바인딩되어 있습니다:

```bash
$ ss -tlnp | grep 5432
LISTEN 0 200 127.0.0.1:5432 0.0.0.0:* users:(("postgres",pid=791,fd=6))
```

그런데 `.env`의 `DB_HOST` 값은 `localhost`(호스트명)입니다. SSH 터널이 이 호스트명을 SSH 서버 쪽에서 해석할 때 **IPv6(`::1`)로 먼저 풀리면**, 아무것도 안 듣고 있는 주소로 포워딩을 시도하다 다음과 같이 타임아웃이 납니다(연결 거부가 아니라 타임아웃인 게 특징입니다):

```
ERROR | Could not establish connection from local (...) to remote ('localhost', 5432) side of the tunnel: open new channel ssh error: Timeout opening channel.
```

**해결책**: 컨테이너 안에서 앱 코드로 DB에 수동 접속할 때(마이그레이션 스크립트 등)는 `DB_HOST` 환경변수를 `127.0.0.1`로 명시적으로 덮어써서 실행해야 합니다. `app/core/config.py`가 `load_dotenv()`를 쓰는데, 이건 기본적으로 이미 설정된 환경변수를 덮어쓰지 않으므로 `docker compose exec -e DB_HOST=127.0.0.1`로 넘긴 값이 `.env`의 `localhost`보다 우선 적용됩니다.

## 컨테이너 안에서 DB에 수동으로 접속/스크립트 실행하는 법

앱과 완전히 같은 방식(SSH 터널)으로 붙어야 하므로, 반드시 **`api` 컨테이너 안에서** 실행해야 합니다(호스트에는 앱 의존성이 없고, `db` 컨테이너 안에서 직접 psql로 붙으면 위에서 설명한 이유로 빈 DB만 보입니다).

### 0. 준비: 컨테이너 안 실제 경로 확인

`Dockerfile`의 `WORKDIR`은 `/app`이지만, **배포된 이미지 버전에 따라 실제 컨테이너의 WORKDIR이 다를 수 있습니다**(2026-07-11 작업 중 한 번은 `/milkywayBot`이었다가, 재배포 후 `/app`으로 바뀐 걸 확인했습니다). 매번 가정하지 말고 먼저 확인하세요:

```bash
docker compose exec api pwd
```

또한 `Dockerfile`이 `scripts/` 디렉토리 전체가 아니라 `scripts/start.sh`만 이미지에 복사하므로, 일회성 스크립트는 컨테이너 재시작/재배포 때마다 다시 넣어줘야 합니다(영구 반영하려면 `Dockerfile`에 `COPY ./scripts /app/scripts` 추가 필요 — 별도 결정 사항).

### 1. 스크립트를 컨테이너에 임시로 넣고 실행

```bash
docker compose exec api mkdir -p /app/scripts
docker compose cp scripts/<파일명>.py api:/app/scripts/<파일명>.py
docker compose exec -e DB_HOST=127.0.0.1 api python scripts/<파일명>.py
```

(WORKDIR이 `/app`이 아니라면 `docker compose exec -w <pwd 결과>` 옵션을 추가로 붙이세요.)

### 2. SQL을 직접 실행하고 싶을 때

`db` 컨테이너가 아니라 호스트의 실제 postgres에 붙어야 하므로, `api` 컨테이너 안에서 앱 코드를 통해 접속하는 것이 가장 확실합니다. 예시(파이썬 one-liner로 쿼리 실행):

```bash
docker compose exec -e DB_HOST=127.0.0.1 api python -c "
import asyncio
from app.core.tunnel import ParamikoTunnel
from app.core.database import create_db_engine
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

async def main():
    tunnel = ParamikoTunnel()
    engine = create_db_engine(tunnel.local_port)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as db:
        result = await db.execute(text('SELECT 1'))
        print(result.all())
    await engine.dispose()
    tunnel.stop()

asyncio.run(main())
"
```

### 자주 하는 실수

- ❌ `docker compose exec db psql ...` — `db` 컨테이너는 앱이 안 쓰는 빈 DB입니다. 항상 잘못된 결과를 보게 됩니다.
- ❌ `DB_HOST` 오버라이드 없이 스크립트 실행 — `localhost`가 IPv6로 풀려서 SSH 터널이 타임아웃 납니다.
- ❌ 컨테이너 경로를 이전 작업 때 확인한 값으로 가정 — 재배포 후 WORKDIR이 바뀔 수 있으니 `pwd`로 매번 확인하세요.
- ❌ DBeaver 등 GUI 툴 연결 정보를 별도로 관리하는 경우, 그게 실제로 이 서버의 postgres를 보고 있는지 확인 없이 신뢰하기 — 실제로 다른 DB를 보고 있었던 사례가 있었습니다(2026-07-11).

## 관련 코드

- `app/core/tunnel.py` — `ParamikoTunnel` (SSH 터널 생성)
- `app/core/database.py` — `create_db_engine(local_port)` (터널 유무에 따라 접속 대상 결정)
- `app/lifespan.py` — 앱 기동 시 위 두 개를 조합해 `app.state.SessionLocal` 초기화
- `scripts/backfill_timer_overlay_css.py` — 위 패턴을 그대로 따르는 일회성 스크립트 예시
