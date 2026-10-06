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
- After creating or modifying Python files, including tests, run Pyright on the changed files with the project's virtual environment: `.venv/Scripts/python.exe -m pyright <changed-python-files> --pythonpath .venv/Scripts/python.exe`.
- Resolve newly introduced type errors before reporting completion. Passing runtime tests alone does not replace type checking.
- Handle optional values explicitly. When a third-party library has inaccurate synchronous/asynchronous type declarations, verify the actual client and return type before using a narrowly scoped `cast`; do not hide errors with blanket type-checking suppression.
