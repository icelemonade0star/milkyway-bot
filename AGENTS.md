# AGENTS.md

## Encoding

- Treat repository text files as UTF-8 with LF line endings.
- On Windows PowerShell, mojibake in command output is not proof that a file is corrupted.
- Before reporting broken Korean text, verify the file bytes with a UTF-8-aware read.
- Prefer one of these checks when Korean text appears garbled:
  - `Get-Content -Encoding UTF8 -Path <file>`
  - `python -B -c "from pathlib import Path; print(Path('<file>').read_text(encoding='utf-8-sig'))"`
  - `[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false); $OutputEncoding = [System.Text.UTF8Encoding]::new($false)`
- Do not rewrite Korean strings solely to fix apparent encoding unless UTF-8 decoding confirms actual file corruption.

## Logging

- Logger call strings (`logger.info`, `logger.error`, `logger.warning`, `logger.debug`, etc.) should be written in Korean.
- Keep code identifiers, external API field names, protocol names, service names, and placeholder labels in their original spelling when that is clearer.
  - Examples: `accessToken`, `data`, `platform`, `status`, `Redis`, `Discord`, `HTTP 401`
  - Wrong: `logger.error("Failed to connect to database")`
  - Correct: `logger.error("데이터베이스 연결 실패")`
  - Correct: `logger.warning("토큰 갱신 실패: accessToken 없음, data=%s", data)`

## Verification

- Run `python scripts/check_utf8.py` after changing text files that may contain Korean.
