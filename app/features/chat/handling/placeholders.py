ATTENDANCE_PLACEHOLDERS = ("[출석일]", "[연속출석일]")


def has_attendance_placeholders(text: str | None) -> bool:
    if not text:
        return False
    return any(token in text for token in ATTENDANCE_PLACEHOLDERS)


def render_placeholders(
    text: str,
    user_name: str | None = None,
    attendance: dict | None = None,
) -> str:
    rendered = text.replace("[닉네임]", user_name or "시청자")

    if attendance is not None:
        rendered = (
            rendered
            .replace("[출석일]", str(attendance.get("total", 0)))
            .replace("[연속출석일]", str(attendance.get("streak", 0)))
        )

    return rendered
