from __future__ import annotations

import json
import logging
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks

from app.core.config import (
    FIXED_LOCAL_ROOT,
    LAST_RUN_ONCE_PATH,
    enforce_local_root_scope,
    is_local_root_in_scope,
    load_config,
    save_config,
)
from app.providers.feishu_legacy import FeishuClient, SyncEngine
from app.providers.feishu_legacy.db import init_db

router = APIRouter(prefix="/api")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tail(path: str, n: int = 200) -> str:
    p = Path(path)
    if not p.exists():
        return ""
    lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[-n:])


def _run_systemctl_user(args: list[str], timeout_sec: int = 4) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["systemctl", "--user", *args],
        capture_output=True,
        text=True,
        timeout=timeout_sec,
        check=False,
    )


def _parse_systemctl_show(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def _build_sync_engine():
    cfg = load_config()
    local_root_locked, requested_local_root = enforce_local_root_scope(cfg)
    init_db(cfg.database.path)

    client = FeishuClient(
        app_id=cfg.auth.app_id,
        app_secret=cfg.auth.app_secret,
        user_token_file=cfg.auth.user_token_file,
        timeout=int(cfg.auth.timeout_sec),
    )

    def log_func(level: str, module: str, message: str, detail: str | None = None):
        logging.getLogger(module).log(
            getattr(logging, level.upper(), logging.INFO),
            f"{message} {detail or ''}".strip(),
        )

    engine = SyncEngine(cfg.model_dump(), cfg.database.path, client, log_func)
    return cfg, engine, local_root_locked, requested_local_root


@router.get("/config")
def get_config():
    cfg = load_config()
    return {
        **cfg.model_dump(),
        "_scope": {
            "fixed_local_root": FIXED_LOCAL_ROOT,
            "configured_local_root": cfg.sync.local_root,
            "out_of_scope": not is_local_root_in_scope(cfg.sync.local_root),
        },
    }


@router.post("/config")
def update_config(payload: dict):
    cfg = load_config()
    merged = cfg.model_dump()

    requested_local_root = None
    for key, value in payload.items():
        if key in ("auth", "sync", "logging", "database") and isinstance(value, dict):
            if key == "sync" and "local_root" in value:
                requested_local_root = value.get("local_root")
            merged.setdefault(key, {})
            merged[key].update(value)
        else:
            merged[key] = value

    cfg2 = cfg.model_validate(merged)
    local_root_locked, locked_from = enforce_local_root_scope(cfg2)
    save_config(cfg2)
    warnings: list[dict[str, str]] = []
    if local_root_locked:
        warnings.append(
            {
                "code": "local_root_scope_locked",
                "requested_local_root": str(locked_from or requested_local_root or ""),
                "applied_local_root": FIXED_LOCAL_ROOT,
            }
        )
    return {"ok": True, "warnings": warnings}


@router.get("/logs")
def get_logs(n: int = 200):
    cfg = load_config()
    return {"path": cfg.logging.file, "tail": _tail(cfg.logging.file, n=n)}


@router.get("/db")
def db_summary():
    cfg = load_config()
    db_path = cfg.database.path
    init_db(db_path)
    if not Path(db_path).exists():
        return {"path": db_path, "exists": False}

    con = sqlite3.connect(db_path)
    cur = con.cursor()
    tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()]
    con.close()
    return {"path": db_path, "exists": True, "tables": tables}


@router.post("/actions/restart")
def restart_service(background: BackgroundTasks):
    def _restart():
        cmd = ["systemctl", "--user", "restart", "localfile-cloudsync.service"]
        subprocess.check_call(cmd)

    background.add_task(_restart)
    return {"ok": True, "message": "restarting"}


@router.get("/status/service")
def service_status():
    unit = "localfile-cloudsync.service"
    out = {
        "ok": False,
        "checked_at": _now_iso(),
        "unit": unit,
        "systemd_available": False,
        "active_state": None,
        "sub_state": None,
        "unit_file_state": None,
        "load_state": None,
        "main_pid": None,
        "status_text": "",
        "error": None,
    }

    try:
        probe = _run_systemctl_user(["--version"], timeout_sec=3)
    except Exception as e:
        out["error"] = str(e)
        return out

    if probe.returncode != 0:
        out["error"] = (probe.stderr or probe.stdout or "systemctl_unavailable").strip()
        return out

    out["systemd_available"] = True

    try:
        show = _run_systemctl_user(
            [
                "show",
                unit,
                "--property",
                "LoadState,ActiveState,SubState,UnitFileState,MainPID,ExecMainCode,ExecMainStatus",
            ],
            timeout_sec=4,
        )
        props = _parse_systemctl_show(show.stdout or "")
        out["load_state"] = props.get("LoadState")
        out["active_state"] = props.get("ActiveState")
        out["sub_state"] = props.get("SubState")
        out["unit_file_state"] = props.get("UnitFileState")
        out["main_pid"] = props.get("MainPID")

        status_cmd = _run_systemctl_user(["status", unit, "--no-pager", "--lines", "8"], timeout_sec=4)
        status_text = (status_cmd.stdout or "").strip()
        if not status_text and status_cmd.stderr:
            status_text = status_cmd.stderr.strip()
        out["status_text"] = status_text

        if not out["load_state"] and out["status_text"]:
            out["error"] = out["status_text"]

        if show.returncode != 0 and not out["status_text"]:
            out["error"] = (show.stderr or show.stdout or "systemctl_show_failed").strip()
        else:
            out["ok"] = bool(out["load_state"])
    except Exception as e:
        out["error"] = str(e)

    return out


@router.get("/status/run-once")
def last_run_once_status():
    if not LAST_RUN_ONCE_PATH.exists():
        return {"exists": False, "path": str(LAST_RUN_ONCE_PATH), "summary": None}
    try:
        return {
            "exists": True,
            "path": str(LAST_RUN_ONCE_PATH),
            "summary": json.loads(LAST_RUN_ONCE_PATH.read_text(encoding="utf-8")),
        }
    except Exception as e:
        return {
            "exists": True,
            "path": str(LAST_RUN_ONCE_PATH),
            "summary": None,
            "error": str(e),
        }


@router.get("/status/feishu")
def feishu_status():
    cfg = load_config()
    user_token_file = cfg.auth.user_token_file
    token_file_path = Path(user_token_file).expanduser() if user_token_file else None

    status = {
        "ok": False,
        "checked_at": _now_iso(),
        "config": {
            "app_id_configured": bool(cfg.auth.app_id),
            "app_secret_configured": bool(cfg.auth.app_secret),
            "user_token_file": user_token_file,
            "user_token_file_exists": bool(token_file_path and token_file_path.exists()),
            "remote_folder_token_configured": bool(cfg.sync.remote_folder_token),
        },
        "token": {
            "available": False,
            "type": None,
            "error": None,
        },
        "connectivity": {
            "api_access": None,
            "root_folder_token": None,
            "error": None,
        },
    }

    try:
        init_db(cfg.database.path)
        client = FeishuClient(
            app_id=cfg.auth.app_id,
            app_secret=cfg.auth.app_secret,
            user_token_file=cfg.auth.user_token_file,
            timeout=int(cfg.auth.timeout_sec),
        )
        token, token_type = client.get_access_token(priority=("user", "tenant"))
        status["token"]["available"] = bool(token)
        status["token"]["type"] = token_type

        if not token:
            status["token"]["error"] = "no_available_token"
            status["connectivity"]["api_access"] = False
            return status

        try:
            root_token = cfg.sync.remote_folder_token or client.get_root_folder_token()
            status["connectivity"]["api_access"] = True
            status["connectivity"]["root_folder_token"] = root_token
            status["ok"] = True
        except Exception as e:
            status["connectivity"]["api_access"] = False
            status["connectivity"]["error"] = str(e)
    except Exception as e:
        status["token"]["error"] = str(e)
        status["connectivity"]["api_access"] = False

    return status


@router.post("/actions/run-once")
def run_once():
    """Run one legacy sync now and return summary."""

    from app.core.last_cmd import record

    record("POST /api/actions/run-once (trigger legacy sync)")
    _cfg, engine, local_root_locked, locked_from = _build_sync_engine()
    summary = engine.run_once(run_type="manual_web")
    if local_root_locked:
        summary["scope_warning"] = {
            "code": "local_root_scope_locked",
            "requested_local_root": str(locked_from or ""),
            "applied_local_root": FIXED_LOCAL_ROOT,
        }
    LAST_RUN_ONCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    LAST_RUN_ONCE_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary
