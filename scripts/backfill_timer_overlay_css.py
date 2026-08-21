"""
scripts/migrate_overlay_kind.sql 실행 직후, 새로 생긴 타이머 오버레이 설정 행 중
style_mode='options'인 행의 custom_css를 실제 옵션값 기반 CSS로 재생성합니다.

SQL 마이그레이션은 timer_custom_css(커스텀 모드일 때만 값이 있음) 값만 그대로
custom_css 컬럼에 옮기기 때문에, 옵션 모드로 쓰던 채널(대부분)은 custom_css가
빈 문자열로 생성됩니다. timer_overlay.html에 기본 스타일 폴백이 있어 완전히
깨지지는 않지만, 백필 전까지는 스트리머가 설정해둔 색상/폰트 등이 반영되지
않고 기본값으로 보입니다. 이 스크립트가 build_timer_overlay_css()를 실제로
호출해서 그 값을 채워 넣습니다.

운영 앱(app/lifespan.py)과 동일하게 ParamikoTunnel을 통해 DB에 접속합니다.
SSH_HOST가 설정된 환경에서 이 컨테이너 밖(호스트)의 postgres가 "localhost"
대신 "127.0.0.1"에만 바인딩되어 있다면(IPv4 전용), DB_HOST를 127.0.0.1로
오버라이드해서 실행해야 SSH 원격 포워딩이 IPv6(::1)로 새지 않습니다.

실행 방법 (api 컨테이너 안에서, 프로젝트 루트에서):
    DB_HOST=127.0.0.1 python scripts/backfill_timer_overlay_css.py

재실행해도 안전합니다(항상 최신 옵션값 기준으로 다시 계산해 덮어씁니다).
"""

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.database import create_db_engine
from app.core.tunnel import ParamikoTunnel
from app.db import models
from app.features.chat_overlay.schemas import TimerOverlayStyleOptions
from app.features.chat_overlay.service import build_timer_overlay_css

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("BackfillTimerOverlayCss")


async def main() -> None:
    # 운영 앱(app/lifespan.py)과 동일하게 SSH 터널을 거쳐 DB에 접속합니다.
    # SSH_HOST가 없으면 tunnel.local_port가 None이 되어 create_db_engine이
    # config.DB_HOST로 직접 접속을 시도합니다(터널이 필요 없는 환경 대비).
    tunnel = ParamikoTunnel()
    engine = create_db_engine(tunnel.local_port)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as db:
        result = await db.execute(
            select(models.V2OverlaySetting).where(
                models.V2OverlaySetting.overlay_kind == "timer",
                models.V2OverlaySetting.style_mode == "options",
            )
        )
        settings = result.scalars().all()
        logger.info("대상 타이머 설정 %d건 발견", len(settings))

        updated = 0
        for setting in settings:
            try:
                options = TimerOverlayStyleOptions.model_validate(setting.style_options or {})
            except Exception as exc:
                logger.warning("channel_id=%s 타이머 옵션 검증 실패, 기본값으로 대체: %s", setting.channel_id, exc)
                options = TimerOverlayStyleOptions()
            setting.custom_css = build_timer_overlay_css(options)  # type: ignore[assignment]  # 레거시 Column() 모델이라 정적 타입 체커가 오탐함
            updated += 1

        await db.commit()
        logger.info("타이머 오버레이 custom_css %d건 재생성 완료", updated)

    await engine.dispose()
    tunnel.stop()


if __name__ == "__main__":
    asyncio.run(main())
