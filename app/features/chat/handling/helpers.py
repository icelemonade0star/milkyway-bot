import json
import re

from app.core.config import ALLOWED_PREFIXES
from app.platforms.constants import PLATFORM_CHZZK

CHAT_PLATFORM = PLATFORM_CHZZK

_EMOTICON_PATTERN = re.compile(r'\{:[a-zA-Z0-9_]+:\}')

ADMIN_SYSTEM_COMMANDS = {
    "명령어등록",
    "명령어삭제",
    "접두사수정",
    "인사등록",
    "인사삭제",
    "알림설정",
    "알림삭제",
}


def strip_prefix(text: str) -> str:
    if text and text[0] in ALLOWED_PREFIXES:
        return text[1:]
    return text


def has_platform_emoticon(text: str) -> bool:
    return bool(_EMOTICON_PATTERN.search(text))


def get_attendance_response_template(response: str, status: str) -> str | None:
    try:
        payload = json.loads(response)
    except (TypeError, json.JSONDecodeError):
        if status in {"checked", "already_checked"}:
            return response
        return None

    if not isinstance(payload, dict):
        return None

    template = payload.get(status)
    if isinstance(template, str) and template.strip():
        return template

    if status == "already_checked":
        checked_template = payload.get("checked")
        if isinstance(checked_template, str) and checked_template.strip():
            return checked_template

    return None


def get_josa(word: str, josa_pair: str) -> str:
    if not word:
        return ""
    last_char = word[-1]
    first, second = josa_pair.split('/')
    if 0xAC00 <= ord(last_char) <= 0xD7A3:
        has_batchim = (ord(last_char) - 0xAC00) % 28 > 0
        return first if has_batchim else second
    elif last_char.isdigit():
        return first if last_char in "013678" else second
    else:
        return second


def parse_command_and_content(args_list):
    if not args_list:
        return None, None

    raw_cmd = args_list[0]
    idx = 1

    while idx < len(args_list):
        next_arg = args_list[idx]
        if raw_cmd.endswith('|') or next_arg.startswith('|'):
            raw_cmd += next_arg
            idx += 1
        else:
            break

    cmd_no_prefix = strip_prefix(raw_cmd)
    cleaned_parts = [p.strip() for p in cmd_no_prefix.split('|') if p.strip()]
    final_cmd = "|".join(cleaned_parts)

    content = " ".join(args_list[idx:]) if idx < len(args_list) else ""

    return final_cmd, content
