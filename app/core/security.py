from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader

import app.core.config as config

api_key_header = APIKeyHeader(name="X-Admin-Token", auto_error=False)


async def verify_admin_token(api_key: str = Security(api_key_header)):
    if not config.ADMIN_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="서버에 ADMIN_TOKEN이 설정되지 않았습니다.",
        )
    if api_key != config.ADMIN_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 관리자 토큰입니다.",
            headers={"WWW-Authenticate": "X-Admin-Token"},
        )
