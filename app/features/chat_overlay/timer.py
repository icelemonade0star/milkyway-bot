import re
import time
from dataclasses import dataclass

from app.features.chat_overlay.broadcaster import timer_overlay_broadcaster


_MAX_TIMER_SECONDS = 24 * 60 * 60
_CLOCK_PATTERN = re.compile(r"^\d{1,2}(?::\d{1,2}){1,2}$")
_UNIT_PATTERN = re.compile(r"(\d+)\s*(시간|시|h|분|m|초|s)", re.IGNORECASE)


@dataclass
class TimerState:
    title: str
    duration_ms: int
    remaining_ms: int
    running: bool
    started_at_ms: int | None = None
    ends_at_ms: int | None = None

    def snapshot(self) -> dict:
        remaining_ms = self.remaining_ms
        if self.running and self.ends_at_ms is not None:
            remaining_ms = max(0, self.ends_at_ms - _now_ms())
        return {
            "title": self.title,
            "duration_ms": self.duration_ms,
            "remaining_ms": remaining_ms,
            "running": self.running and remaining_ms > 0,
            "started_at_ms": self.started_at_ms,
            "ends_at_ms": self.ends_at_ms if remaining_ms > 0 else None,
        }


def _now_ms() -> int:
    return int(time.time() * 1000)


def parse_timer_duration(raw: str) -> int | None:
    value = raw.strip().lower()
    if not value:
        return None

    if _CLOCK_PATTERN.fullmatch(value):
        parts = [int(part) for part in value.split(":")]
        if len(parts) == 2:
            minutes, seconds = parts
            total = minutes * 60 + seconds
        else:
            hours, minutes, seconds = parts
            total = hours * 3600 + minutes * 60 + seconds
        return total if 0 < total <= _MAX_TIMER_SECONDS and minutes < 60 and seconds < 60 else None

    if value.isdigit():
        total = int(value) * 60
        return total if 0 < total <= _MAX_TIMER_SECONDS else None

    total = 0
    matched = False
    consumed = ""
    for match in _UNIT_PATTERN.finditer(value):
        matched = True
        consumed += match.group(0)
        amount = int(match.group(1))
        unit = match.group(2)
        if unit in {"시간", "시", "h"}:
            total += amount * 3600
        elif unit in {"분", "m"}:
            total += amount * 60
        else:
            total += amount

    if not matched:
        return None
    if re.sub(r"\s+", "", consumed) != re.sub(r"\s+", "", value):
        return None
    return total if 0 < total <= _MAX_TIMER_SECONDS else None


class OverlayTimerManager:
    def __init__(self):
        self._states: dict[str, TimerState] = {}

    def get_snapshot(self, channel_id: str) -> dict | None:
        state = self._states.get(channel_id)
        return state.snapshot() if state else None

    async def publish_snapshot(self, channel_id: str):
        snapshot = self.get_snapshot(channel_id)
        if snapshot:
            await timer_overlay_broadcaster.publish(
                channel_id,
                {"type": "timer", "action": "snapshot", "timer": snapshot},
            )

    async def set_timer(self, channel_id: str, title: str, seconds: int, autoplay: bool):
        now = _now_ms()
        duration_ms = seconds * 1000
        state = TimerState(
            title=title,
            duration_ms=duration_ms,
            remaining_ms=duration_ms,
            running=autoplay,
            started_at_ms=now if autoplay else None,
            ends_at_ms=now + duration_ms if autoplay else None,
        )
        self._states[channel_id] = state
        await self.publish_snapshot(channel_id)

    async def play(self, channel_id: str) -> bool:
        state = self._states.get(channel_id)
        if not state:
            return False
        snapshot = state.snapshot()
        remaining_ms = snapshot["remaining_ms"]
        if remaining_ms <= 0:
            remaining_ms = state.duration_ms
        now = _now_ms()
        state.remaining_ms = remaining_ms
        state.running = True
        state.started_at_ms = now
        state.ends_at_ms = now + remaining_ms
        await self.publish_snapshot(channel_id)
        return True

    async def pause(self, channel_id: str) -> bool:
        state = self._states.get(channel_id)
        if not state:
            return False
        snapshot = state.snapshot()
        state.remaining_ms = snapshot["remaining_ms"]
        state.running = False
        state.started_at_ms = None
        state.ends_at_ms = None
        await self.publish_snapshot(channel_id)
        return True

    async def clear(self, channel_id: str) -> bool:
        existed = self._states.pop(channel_id, None) is not None
        await timer_overlay_broadcaster.publish(
            channel_id,
            {"type": "timer", "action": "delete"},
        )
        return existed


overlay_timer_manager = OverlayTimerManager()
