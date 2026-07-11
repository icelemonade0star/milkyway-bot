"""
scripts/migrate_overlay_kind.sql 실행 직후, 새로 생긴 타이머 오버레이 설정 행 중
style_mode='options'인 행의 custom_css를 실제 옵션값 기반 CSS로 재생성합니다.

SQL 마이그레이션은 timer_custom_css(커스텀 모드일 때만 값이 있음) 값만 그대로
custom_css 컬럼에 옮기기 때문에, 옵션 모드로 쓰던 채널(대부분)은 custom_css가
빈 문자열로 생성됩니다. timer_overlay.html에 기본 스타일 폴백이 있어 완전히
깨지지는 않지만, 백필 전까지는 스트리머가 설정해둔 색상/폰트 등이 반영되지
않고 기본값으로 보입니다. 이 스크립트가 build_timer_overlay_css()를 실제로
호출해서 그 값을 채워 넣습니다.

실행 방법 (프로젝트 루트에서):
    .venv/Scripts/python.exe scripts/backfill_timer_overlay_css.py   (Windows)
    .venv/bin/python scripts/backfill_timer_overlay_css.py           (Linux)

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
from app.db import models
from app.features.chat_overlay.schemas import TimerOverlayStyleOptions
from app.features.chat_overlay.service import build_timer_overlay_css

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("BackfillTimerOverlayCss")


async def main() -> None:
    engine = create_db_engine(local_port=None)
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
            setting.custom_css = build_timer_overlay_css(options)
            updated += 1

        await db.commit()
        logger.info("타이머 오버레이 custom_css %d건 재생성 완료", updated)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
