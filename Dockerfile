ARG PYTHON_VERSION=3.13.9
FROM python:${PYTHON_VERSION}-slim AS builder

WORKDIR /app
ENV PYTHONPATH=/app

# 가상환경 생성
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 의존성 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 프로덕션 스테이지
FROM python:${PYTHON_VERSION}-slim AS final

WORKDIR /app
ENV PYTHONPATH=/app

# 가상환경 복사
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 애플리케이션 코드 복사
COPY ./app /app/app

# 시작 스크립트 복사
COPY ./scripts/start.sh /app/start.sh
RUN chmod +x /app/start.sh

CMD ["/app/start.sh"]