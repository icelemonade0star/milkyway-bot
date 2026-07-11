from pydantic import ValidationError

from app.features.chat_overlay.schemas import TimerOverlayStyleOptions
from app.features.chat_overlay.service import ChatOverlayService
from app.features.chat_overlay.timer import overlay_timer_manager, parse_timer_duration
from app.platforms.constants import PLATFORM_CHZZK


async def _get_timer_options(chat_service, channel_id: str) -> TimerOverlayStyleOptions:
    try:
        row = await ChatOverlayService(chat_service.db).get_setting_by_channel(PLATFORM_CHZZK, channel_id, "timer")
        if not row:
            return TimerOverlayStyleOptions()
        _channel, setting = row
        return TimerOverlayStyleOptions.model_validate(setting.style_options or {})
    except ValidationError:
        return TimerOverlayStyleOptions()


async def handle_timer_command(session, chat_service, channel_id: str, args: list[str]):
    if not args:
        await session.send_chat("사용법: !타이머 [시간] 또는 !타이머 [제목] [시간] / !타이머 재생|정지|삭제")
        return

    subcommand = args[0].strip()
    if len(args) == 1 and subcommand == "재생":
        if await overlay_timer_manager.play(channel_id):
            await session.send_chat("타이머를 재생했습니다.")
        else:
            await session.send_chat("재생할 타이머가 없습니다.")
        return

    if len(args) == 1 and subcommand == "정지":
        if await overlay_timer_manager.pause(channel_id):
            await session.send_chat("타이머를 정지했습니다.")
        else:
            await session.send_chat("정지할 타이머가 없습니다.")
        return

    if len(args) == 1 and subcommand == "삭제":
        await overlay_timer_manager.clear(channel_id)
        await session.send_chat("타이머를 삭제했습니다.")
        return

    duration_arg = args[-1]
    duration_seconds = parse_timer_duration(duration_arg)
    if duration_seconds is None:
        await session.send_chat("시간 형식이 올바르지 않습니다. 예: 10, 10분, 90초, 01:30, 1:00:00")
        return

    timer_options = await _get_timer_options(chat_service, channel_id)
    title = " ".join(args[:-1]).strip() or timer_options.timer_title_text
    autoplay = timer_options.timer_autoplay

    await overlay_timer_manager.set_timer(channel_id, title, duration_seconds, autoplay)
    status = "시작" if autoplay else "대기"
    await session.send_chat(f"타이머 '{title}' {duration_arg} {status}.")
