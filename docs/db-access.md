# 서버 DB 접속 방법

## 핵심 요약 (2026-07-18 이관 완료)

운영 PostgreSQL은 `docker-compose.yml`의 `db` 서비스(`postgres:18.1`, `milkywaybot-db-1`)입니다. 호스트에 직접 설치돼 있던 PostgreSQL을 데이터 디렉토리 그대로(`/var/lib/postgresql/18/main` bind mount) 컨테이너로 이전했고, 호스트 쪽 `postgresql@18-main` 서비스는 정지된 상태입니다.

`api` 컨테이너는 도커 네트워크 안에서 서비스명 `db:5432`로 직접 접속합니다. **SSH 터널을 거치는 과거 구조는 완전히 폐기됐습니다** — `.env`의 `SSH_HOST`가 비어있으면 `app/core/tunnel.py`의 `ParamikoTunnel`이 터널을 만들지 않고 `config.DB_HOST`(`db`)로 바로 접속합니다.

## DB에 직접 접속하는 법

### 컨테이너 안에서 psql로 접속

```bash
docker compose exec db psql -h 127.0.0.1 -U api_user -d milkyway_db
```

`db` 서비스는 `user: "112:113"`(비-root)로 뜨기 때문에 유닉스 소켓(`peer` 인증)이 아니라 반드시 `-h 127.0.0.1`(TCP)로 접속해야 합니다.

### 호스트에서 DBeaver 등 GUI 툴로 접속

`db` 서비스에 `ports: ["127.0.0.1:5432:5432"]`가 게시돼 있어서, 서버에 SSH로 접속한 뒤(또는 로컬 SSH 터널로) `127.0.0.1:5432`로 그대로 붙으면 됩니다(예전 호스트 직접설치 postgres와 동일한 접속 방식이라 DBeaver 설정 변경 불필요).

### 컨테이너 안에서 앱 코드로 스크립트 실행

`api` 컨테이너 안에서 실행하면 `.env`에 설정된 `DB_HOST=db`를 그대로 써서 앱과 동일한 경로로 접속합니다. `SSH_HOST` 오버라이드나 별도 처리가 필요 없습니다.

```bash
docker compose exec api mkdir -p /app/scripts
docker compose cp scripts/<파일명>.py api:/app/scripts/<파일명>.py
docker compose exec api python scripts/<파일명>.py
```

`Dockerfile`이 `scripts/start.sh`만 이미지에 복사하므로, 일회성 스크립트는 컨테이너 재배포 때마다 다시 넣어줘야 합니다.

## `api` 컨테이너를 서버에서 수동으로 재기동할 때 (중요)

`docker-compose.yml`의 `api` 이미지 태그는 다음과 같이 정의돼 있습니다.

```yaml
image: ${DOCKERHUB_USERNAME}/milkyway_bot:${DEPLOY_SHA:-latest}
```

`DEPLOY_SHA` 셸 환경변수를 지정하지 않고 `docker compose up -d api` / `restart api` / `up -d --force-recreate api`를 실행하면 태그가 `:latest`로 해석됩니다. **로컬에 이미 `:latest` 태그의 이미지가 캐시돼 있으면 `docker compose up -d`는 pull을 생략하고 그 캐시를 그대로 씁니다** — CD가 배포 때마다 `${DEPLOY_SHA}` 태그로만 pull하고 `:latest` 태그 자체는 갱신하지 않기 때문에, 그 캐시된 `:latest`는 몇 주~몇 달 전의, 심하면 스키마 마이그레이션 이전의 아주 오래된 이미지일 수 있습니다.

**2026-07-18에 이 문제로 두 번 실제 장애를 겪었습니다**: 낡은 이미지가 뜨면서 API 응답은 정상(200 OK)이지만 내부적으로는 완전히 다른(구버전) 코드와 스키마 매핑으로 동작해, 인증 목록 조회·채팅 세션 복구 등이 조용히 오작동했습니다. 에러 로그도 남지 않아 원인 파악이 매우 어려웠습니다.

**규칙**: 서버에서 `api`를 수동으로 재기동/재생성할 때는 반드시 먼저 최신 SHA를 지정하세요.

```bash
git fetch origin
export DEPLOY_SHA=$(git rev-parse origin/main)
docker compose pull api
docker compose up -d api
```

재기동 후에는 이미지가 실제로 최신인지 확인하는 습관을 들이는 게 좋습니다(예: `docker compose exec api python3 -c "import app.db.models as m; print('V2Channel' in dir(m))"`가 `True`인지 등).

## 자주 하는 실수

- ❌ `DEPLOY_SHA` 없이 `api`를 수동 재기동 — 위 섹션 참고. 캐시된 낡은 `:latest` 이미지가 뜰 수 있습니다.
- ❌ 컨테이너 경로를 이전 작업 때 확인한 값으로 가정 — 재배포 후 `WORKDIR`이 바뀔 수 있으니 `docker compose exec api pwd`로 매번 확인하세요.
- ❌ DBeaver 등 GUI 툴 연결 정보를 별도로 관리하는 경우, 그게 실제로 이 서버의 `db` 컨테이너를 보고 있는지 확인 없이 신뢰하기.

## 관련 코드

- `app/core/tunnel.py` — `ParamikoTunnel` (SSH_HOST가 설정된 경우에만 터널 생성, 현재는 비어있어 no-op)
- `app/core/database.py` — `create_db_engine(local_port)` (터널 유무에 따라 접속 대상 결정, 현재는 `config.DB_HOST` 직접 사용)
- `app/lifespan.py` — 앱 기동 시 위 두 개를 조합해 `app.state.SessionLocal` 초기화
