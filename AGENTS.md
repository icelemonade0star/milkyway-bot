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

## Verification

- Run `python scripts/check_utf8.py` after changing text files that may contain Korean.
