#!/bin/bash
set -e

# (선택) 마이그레이션 등 사전 작업이 있으면 여기서 실행
# alembic upgrade head

# Uvicorn으로 앱 실행
exec uvicorn app.main:app --host 0.0.0.0 --port 8000