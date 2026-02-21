from __future__ import annotations

from datetime import datetime
from pathlib import Path

from app.core.config import RUNTIME_DIR

LAST_CMD_FILE = RUNTIME_DIR / "last_cmd.txt"
HISTORY_FILE = RUNTIME_DIR / "last_cmd_history.log"


def record(cmd: str):
    LAST_CMD_FILE.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    LAST_CMD_FILE.write_text(f"{cmd}\n", encoding="utf-8")
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY_FILE.open("a", encoding="utf-8") as f:
        f.write(f"{ts} {cmd}\n")


def record_step(step: str):
    record(f"DEVSTEP: {step}")
