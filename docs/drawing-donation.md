# 그림 도네이션

시청자가 프로젝트 안의 그림 페이지에서 그린 기록과 완성 PNG를 저장하고, 발급받은 `#mw-…` 해시태그를 치지직 후원 메시지에 넣으면 OBS 오버레이에서 그린 과정을 재생합니다. 같은 그림 해시태그도 후원 이벤트마다 새로운 재생 항목을 추가합니다.

## 설치와 진입

운영 반영 전에 기존 PostgreSQL에 신규 테이블 세 개를 생성합니다. 이 스크립트는 기존 테이블과 데이터를 변경하지 않습니다.

```bash
docker compose exec -T db psql -h 127.0.0.1 -U api_user -d milkyway_db -v ON_ERROR_STOP=1 < scripts/create_drawing_donation_tables.sql
```

DB 사용자와 데이터베이스 이름은 서버 설정에 맞게 변경하세요. PowerShell에서는 파일 내용을 UTF-8로 읽어 `psql` 입력으로 전달하거나 DB 도구에서 SQL을 실행할 수 있습니다. 테이블 생성 후 새 코드를 배포하고 서버를 재시작합니다. 앱은 기존 프로젝트와 같이 자동 스키마 변경을 수행하지 않습니다.

`fastapi.conf` 변경도 반영해야 합니다. 그림 저장 경로는 Nginx의 업로드 허용 크기를 `5m`으로 설정하고 본문 버퍼링을 꺼서 앱이 저장 제한을 먼저 검사하게 합니다. CD는 매번 원본 설정을 `nginx-runtime/fastapi.conf`로 복사하고, API 기동 확인 후 `nginx -t`에 성공하면 `nginx -s reload`를 실행합니다. 검사에 실패하면 배포도 실패하고 reload는 실행하지 않습니다.

Nginx는 `nginx-runtime/` 디렉터리를 읽기 전용으로 마운트하므로 Git이 원본 파일을 교체해도 최신 설정을 읽습니다. 마운트 구조가 바뀌는 최초 배포에서는 Nginx 컨테이너가 한 번 재생성될 수 있습니다. 이후 배포에서는 명시적인 재시작 없이 검사와 reload를 실행합니다. 기존 메모리 제한 `64m`은 유지합니다.

CD를 거치지 않고 처음 Compose를 실행하는 경우에는 프로젝트 디렉터리에서 아래 명령으로 설정 파일을 먼저 준비하세요. 수동 설정 변경 후에도 복사 → 검사 → reload 순서로 반영합니다.

```bash
mkdir -p nginx-runtime
cp fastapi.conf nginx-runtime/fastapi.conf
```

1. 대시보드의 **그림 도네이션**(`/auth/dashboard/drawing`)으로 이동합니다.
2. **그림 도네이션 받기**를 켜고 최소 후원 금액, 재생 시간, 완성본 표시 시간, 너비, 후원자 표시를 저장합니다. 기본값은 비활성, 1,000원, 20초 재생, 5초 완성본 표시입니다.
3. 그림 페이지 링크(`/drawing/chzzk/{channel_id}`)를 시청자에게 공유합니다.
4. 방송용 OBS 링크를 브라우저 소스에 등록합니다. 링크의 토큰은 방송 오버레이 접근용이므로 시청자에게는 그림 페이지 링크만 공유합니다.
5. **테스트 그림 재생**은 미리보기에서만 동작하며 실제 대기열을 소비하지 않습니다.

## 저장과 재생

- 캔버스는 800 × 600이며 펜, 색상, 굵기, 지우개, 되돌리기, 모두 지우기를 지원합니다. 좌표와 순서, 상대 시간, 도구를 기록합니다.
- 최대 10분, 25,000개 포인트, 2,000개 동작을 기록합니다. 완성본 PNG는 약 2MB, 저장 요청 전체는 5MB로 제한합니다.
- 공개 저장 API는 로그인 없이 사용하며 Redis로 IP당 분당 5회·시간당 30회 요청을 제한합니다. 본문을 읽기 전에 검사하므로 새 `save_key`를 발급하거나 채널을 바꿔도 같은 IP 제한을 공유합니다. 전체 요청 본문은 90분 제한 구간마다 128MB까지 허용합니다. 재시도와 잘못된 요청도 제한에 포함되며, 초과 시 HTTP 429와 `Retry-After`를 반환합니다. Redis 장애 중에는 저장만 HTTP 503으로 중단합니다.
- 제한값은 `DRAWING_DONATION_SAVE_PER_MINUTE`, `DRAWING_DONATION_SAVE_PER_HOUR`, `DRAWING_DONATION_SAVE_BYTE_BUDGET`로 조정할 수 있습니다. 전체 요청량 제한은 DB 용량 자체의 정확한 상한은 아닙니다. 제한 구간 경계의 요청과 DB 저장 오버헤드를 고려해야 합니다.
- Docker Compose는 내부 전용 API 앞에서 Nginx가 `X-Real-IP`를 덮어쓰므로 `DRAWING_DONATION_TRUST_PROXY_HEADERS=true`를 설정합니다. Compose 변경도 배포 시 반영하세요. API를 직접 공개하는 구성에서는 이 옵션을 끄세요(기본값 `false`). 임의 `X-Forwarded-For`는 저장 제한에서 사용하지 않습니다.
- 동일한 저장 요청을 재시도해도 같은 해시태그를 반환합니다. 저장한 그림을 수정하면 새로운 저장 식별자를 사용합니다.
- 그림과 해시태그는 저장 후 1시간 동안 사용할 수 있습니다. `expires_at`는 사용 만료 시각입니다. 만료된 그림은 DB 삭제 전이라도 새 후원 접수와 재생을 제한하며, 동일 저장 요청을 재시도해도 유효기간을 연장하지 않습니다.
- 서버 시작 시 즉시 한 번 정리하고, 이후 기본 30분마다 만료된 그림을 배치 삭제합니다. 정상 실행 시 실제 데이터는 보통 저장 후 약 1~1.5시간 안에 삭제됩니다. 완성 PNG, 그리기 기록과 연결된 대기·재생·완료 항목을 함께 삭제합니다. 채널 설정과 OBS 링크는 유지합니다.
- 서버가 중지된 동안 만료된 데이터는 다음 시작 시 정리합니다. 정리 주기는 `DRAWING_DONATION_CLEANUP_INTERVAL_SECONDS`로 설정할 수 있습니다(기본 `1800`).
- 현재 완성 PNG와 그리기 기록은 모두 DB에 저장하므로 별도의 디스크 파일 삭제 작업은 없습니다.
- 해당 채널의 활성 설정, 최소 금액, 그림 소속 채널, 유효기간을 확인합니다. 여러 태그가 있으면 앞에서부터 처음 찾은 유효한 그림 하나를 접수합니다.
- 금액은 숫자로 구성된 `payAmount` 문자열 또는 정수만 처리합니다. 익명 후원은 후원자 ID 없이도 동작합니다.
- `DONATION` 수신 이벤트마다 대기열에 등록합니다. 치지직 명세에 고유 후원 ID가 없으므로 서로 다른 후원을 메시지·금액·닉네임이 같다는 이유로 합치지 않습니다.
- 재생은 원래 동작 순서와 상대 시간 비율을 유지해 설정한 시간에 맞춥니다. 재생 후 저장된 완성 PNG를 표시합니다.
- OBS가 연결되지 않은 동안의 후원은 DB 대기열에 남아있습니다. OBS 연결 시 재생을 시작합니다. 여러 OBS 창은 같은 항목과 경과 시간을 공유합니다.
- 재생 상태와 시작 시간을 DB에 저장합니다. 서버 또는 OBS 재연결 시 진행 상태를 복구하며, 이미 표시 시간이 지난 항목은 다음 그림으로 넘어갑니다.
- 설정에서 수신을 끄면 저장과 신규 후원 접수를 중단하고 오버레이를 숨깁니다. 이미 접수된 대기열은 유지합니다.

## 구현 위치와 검증

- `app/features/drawing_donation/`: 기록 검증, 저장, 후원 매칭, 대기열, 화면 및 API
- `app/features/chat/handling/events.py`: `DONATION` 이벤트 연결
- `app/static/js/drawing_canvas.js`: 편집과 재생에서 공유하는 그리기 코드
- `scripts/create_drawing_donation_tables.sql`: PostgreSQL 신규 스키마
- `app/features/drawing_donation/cleanup.py`: 서버 수명 주기에 연결된 만료 데이터 정리 작업
- `tests/test_drawing_donation.py`: 저장/API/금액/채널 분리/반복 후원/대기열 검증. 로컬 SQLite로 영속성 흐름을 확인합니다.
- `tests/test_drawing_browser.py`: 실제 Chromium에서 그리기·지우기·되돌리기·저장·PNG 재생 일치, 모바일 배치, 미리보기의 대기열 분리 검증

```bash
python -m pip install -r requirements-test.txt
python -m playwright install chromium
python -m pytest -p no:cacheprovider tests/test_drawing_donation.py tests/test_drawing_browser.py tests/test_session_events.py tests/test_command_routing.py tests/test_attendance_cooldown.py tests/test_attendance_retry.py -q
python scripts/check_utf8.py
```

CI도 Redis Lua 테스트 도구와 Chromium을 설치하고 관련 타입 검사 및 브라우저 테스트를 실행합니다. PostgreSQL의 행 잠금과 운영 치지직 후원 수신은 운영 반영 후 추가 확인이 필요합니다. OBS 링크로 활성 그림을 확인하고, 실제 후원에 저장된 해시태그를 포함해 재생되는지 확인합니다.
