from pydantic import ValidationError

from app.features.chat_overlay.schemas import OverlayStyleOptions
from app.features.chat_overlay.service import ChatOverlayService
from app.features.chat_overlay.timer import overlay_timer_manager, parse_timer_duration
from app.platforms.constants import PLATFORM_CHZZK


_AUTOPLAY_ON = {"자동재생", "--자동재생", "autoplay", "--autoplay"}
_AUTOPLAY_OFF = {"수동", "--수동", "manual", "--manual", "대기", "--대기"}


def _extract_autoplay(args: list[str]) -> tuple[list[str], bool | None]:
    autoplay: bool | None = None
    cleaned: list[str] = []
    for arg in args:
        normalized = arg.strip().casefold()
        if normalized in _AUTOPLAY_ON:
            autoplay = True
            continue
        if normalized in _AUTOPLAY_OFF:
            autoplay = False
            continue
        cleaned.append(arg)
    return cleaned, autoplay


async def _get_timer_autoplay(chat_service, channel_id: str) -> bool:
    try:
        row = await ChatOverlayService(chat_service.db).get_setting_by_channel(PLATFORM_CHZZK, channel_id)
        if not row:
            return True
        _channel, setting = row
        options = OverlayStyleOptions.model_validate(setting.style_options or {})
        return options.timer_autoplay
    except ValidationError:
        return True


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

    cleaned_args, command_autoplay = _extract_autoplay(args)
    if not cleaned_args:
        await session.send_chat("타이머 시간을 입력해 주세요.")
        return

    duration_arg = cleaned_args[-1]
    duration_seconds = parse_timer_duration(duration_arg)
    if duration_seconds is None:
        await session.send_chat("시간 형식이 올바르지 않습니다. 예: 10, 10분, 90초, 01:30, 1:00:00")
        return

    title = " ".join(cleaned_args[:-1]).strip() or "타이머"
    autoplay = command_autoplay
    if autoplay is None:
        autoplay = await _get_timer_autoplay(chat_service, channel_id)

    await overlay_timer_manager.set_timer(channel_id, title, duration_seconds, autoplay)
    status = "시작" if autoplay else "대기"
    await session.send_chat(f"타이머 '{title}' {duration_arg} {status}.")
