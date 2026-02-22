from __future__ import annotations

import re
from pathlib import Path


LOG_LINE_RE = re.compile(
    r"^(?P<ts>\S+\s+\S+)\s+\[(?P<level>[A-Z]+)\]\s+\[(?P<module>[^\]]+)\]\s*(?P<message>.*)$"
)


def _tail_lines(path: str, n: int = 200) -> list[str]:
    p = Path(path)
    if not p.exists():
        return []
    lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    return lines[-n:]


def _parse_line(line: str) -> dict[str, str]:
    match = LOG_LINE_RE.match(line)
    if not match:
        return {"raw": line, "level": "", "module": "", "message": line}
    parsed = match.groupdict()
    return {
        "raw": line,
        "level": parsed.get("level", ""),
        "module": parsed.get("module", ""),
        "message": parsed.get("message", ""),
    }


def build_log_tail_payload(path: str, n: int = 200, level: str | None = None, module: str | None = None) -> dict:
    level_wanted = (level or "").strip().upper() or None
    module_wanted = (module or "").strip().lower() or None

    parsed_lines: list[dict[str, str]] = []
    for line in _tail_lines(path, n=n):
        item = _parse_line(line)
        if level_wanted and item["level"].upper() != level_wanted:
            continue
        if module_wanted and item["module"].strip().lower() != module_wanted:
            continue
        parsed_lines.append(item)

    return {
        "path": path,
        "n": n,
        "level": level_wanted,
        "module": module_wanted,
        "count": len(parsed_lines),
        "tail": "\n".join(item["raw"] for item in parsed_lines),
        "items": parsed_lines,
    }
