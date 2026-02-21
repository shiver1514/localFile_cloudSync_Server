from __future__ import annotations

import logging
from pathlib import Path


def setup_logging(level: str, logfile: str):
    Path(logfile).parent.mkdir(parents=True, exist_ok=True)

    log_level = getattr(logging, level.upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(log_level)

    # Clear existing handlers to avoid duplicates across restarts/reloads.
    for h in list(root.handlers):
        root.removeHandler(h)

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] [%(name)s] %(message)s")

    fh = logging.FileHandler(logfile, encoding="utf-8")
    fh.setLevel(log_level)
    fh.setFormatter(fmt)
    root.addHandler(fh)

    ch = logging.StreamHandler()
    ch.setLevel(log_level)
    ch.setFormatter(fmt)
    root.addHandler(ch)

    # Route uvicorn logs into the same root handlers/file.
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(logger_name)
        logger.handlers.clear()
        logger.setLevel(log_level)
        logger.propagate = True

    root.info("logging initialized")
