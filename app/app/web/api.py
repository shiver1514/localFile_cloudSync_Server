from __future__ import annotations

import asyncio
import base64
import fnmatch
import hashlib
import json
import logging
import secrets
import sqlite3
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypedDict

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import JSONResponse

from app.core.config import (
    AUTH_STATE_PATH,
    FIXED_LOCAL_ROOT,
    LAST_RUN_ONCE_PATH,
    RUN_HISTORY_PATH,
    enforce_local_root_scope,
    is_local_root_in_scope,
    load_config,
    save_config,
)
from app.core.log_tail import build_log_tail_payload
from app.providers.feishu_legacy import FeishuClient, SyncEngine
from app.providers.feishu_legacy.db import init_db

try:
    from Crypto.Cipher import AES
except Exception:  # pragma: no cover - optional dependency in runtime
    AES = None  # type: ignore[assignment]

router = APIRouter(prefix="/api")

SYNC_RUN_LOCK = threading.Lock()
SCHEDULER_STATE_LOCK = threading.Lock()
SCHEDULER_POLL_GRANULARITY_SEC = 1
SCHEDULER_MIN_INTERVAL_SEC = 10
SCHEDULER_MAX_INTERVAL_SEC = 86400

_scheduler_task: asyncio.Task | None = None
_scheduler_stop_event: asyncio.Event | None = None
_scheduler_state: dict[str, object] = {
    "running": False,
    "enabled": False,
    "configured_interval_sec": 0,
    "effective_interval_sec": 0,
    "last_started_at": None,
    "last_finished_at": None,
    "last_result": None,
    "last_error": None,
    "next_run_at": None,
    "skipped_busy_count": 0,
    "run_count": 0,
}

EVENT_STATE_LOCK = threading.Lock()
EVENT_MIN_DEBOUNCE_SEC = 0
EVENT_MAX_DEBOUNCE_SEC = 3600
EVENT_LOCK_WAIT_TIMEOUT_SEC = 120
EVENT_DEDUP_TTL_SEC = 600
EVENT_DEFAULT_TRIGGER_TYPES = [
    "drive.file.edit_v1",
    "drive.file.title_updated_v1",
    "drive.file.created_in_folder_v1",
    "drive.file.deleted_v1",
    "drive.file.trashed_v1",
    "drive.file.bitable_record_changed_v1",
    "drive.file.bitable_field_changed_v1",
]

_event_state: dict[str, object] = {
    "enabled": False,
    "verify_token_configured": False,
    "encrypt_key_configured": False,
    "debounce_sec": 15,
    "trigger_types": list(EVENT_DEFAULT_TRIGGER_TYPES),
    "pending": False,
    "last_received_at": None,
    "last_event_type": None,
    "last_event_id": None,
    "last_challenge_at": None,
    "last_trigger_requested_at": None,
    "last_triggered_at": None,
    "last_result": None,
    "last_error": None,
    "received_count": 0,
    "trigger_count": 0,
    "skipped_unmatched_count": 0,
    "skipped_debounce_count": 0,
    "skipped_busy_count": 0,
    "skipped_pending_count": 0,
    "skipped_disabled_count": 0,
    "duplicate_count": 0,
}
_event_recent_ids: dict[str, float] = {}


class EventRuntimeSettings(TypedDict):
    enabled: bool
    verify_token: str
    encrypt_key: str
    debounce_sec: int
    trigger_types: list[str]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _append_run_history(summary: dict) -> None:
    RUN_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with RUN_HISTORY_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(summary, ensure_ascii=False))
        f.write("\n")


def _read_run_history(limit: int = 50) -> list[dict]:
    if limit <= 0:
        return []
    if not RUN_HISTORY_PATH.exists():
        return []

    lines = RUN_HISTORY_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
    out: list[dict] = []
    for line in reversed(lines):
        if len(out) >= limit:
            break
        raw = line.strip()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except Exception:
            payload = {"raw": raw, "parse_error": True}
        if isinstance(payload, dict):
            out.append(payload)
    return out


def _load_latest_run_summary() -> tuple[dict[str, Any] | None, str, str | None]:
    """
    Return latest run summary with source:
    - last_run_once: runtime/last_run_once.json
    - history_fallback: runtime/run_history.jsonl latest item
    - none: no summary available
    """
    parse_error: str | None = None
    if LAST_RUN_ONCE_PATH.exists():
        try:
            payload = json.loads(LAST_RUN_ONCE_PATH.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return payload, "last_run_once", None
            parse_error = "last_run_once_not_object"
        except Exception as e:
            parse_error = str(e)

    items = _read_run_history(limit=1)
    if items:
        latest = items[0]
        if isinstance(latest, dict):
            return latest, "history_fallback", parse_error
    return None, "none", parse_error


def _as_int(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return default
        try:
            return int(raw)
        except ValueError:
            return default
    return default


def _as_float(value: object) -> float | None:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        try:
            return float(raw)
        except ValueError:
            return None
    return None


def _sanitize_poll_interval(raw_value: object) -> int:
    raw = _as_int(raw_value, 0)
    if raw <= 0:
        return 0
    return min(max(raw, SCHEDULER_MIN_INTERVAL_SEC), SCHEDULER_MAX_INTERVAL_SEC)


def _iso_from_ts(ts: object) -> str | None:
    value = _as_float(ts)
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()
    except Exception:
        return None


def _scheduler_state_update(**kwargs) -> None:
    with SCHEDULER_STATE_LOCK:
        _scheduler_state.update(kwargs)


def _scheduler_state_snapshot() -> dict[str, object]:
    with SCHEDULER_STATE_LOCK:
        snap = dict(_scheduler_state)

    now_ts = time.time()
    next_run_at_raw = snap.get("next_run_at")
    next_run_at = _as_float(next_run_at_raw)
    if next_run_at is None:
        next_run_in_sec = None
    else:
        next_run_in_sec = max(int(next_run_at - now_ts), 0)

    return {
        "running": bool(snap.get("running")),
        "enabled": bool(snap.get("enabled")),
        "configured_interval_sec": _as_int(snap.get("configured_interval_sec"), 0),
        "effective_interval_sec": _as_int(snap.get("effective_interval_sec"), 0),
        "last_started_at": _iso_from_ts(snap.get("last_started_at")),
        "last_finished_at": _iso_from_ts(snap.get("last_finished_at")),
        "next_run_at": _iso_from_ts(next_run_at_raw),
        "next_run_in_sec": next_run_in_sec,
        "last_result": snap.get("last_result"),
        "last_error": snap.get("last_error"),
        "run_count": _as_int(snap.get("run_count"), 0),
        "skipped_busy_count": _as_int(snap.get("skipped_busy_count"), 0),
    }


def _sanitize_event_debounce(raw_value: object) -> int:
    raw = _as_int(raw_value, 15)
    return min(max(raw, EVENT_MIN_DEBOUNCE_SEC), EVENT_MAX_DEBOUNCE_SEC)


def _normalize_event_trigger_types(raw_value: object) -> list[str]:
    if isinstance(raw_value, list):
        items = raw_value
    else:
        items = EVENT_DEFAULT_TRIGGER_TYPES
    out: list[str] = []
    for item in items:
        value = str(item or "").strip()
        if not value:
            continue
        out.append(value)
    return out or list(EVENT_DEFAULT_TRIGGER_TYPES)


def _event_state_update(**kwargs) -> None:
    with EVENT_STATE_LOCK:
        _event_state.update(kwargs)


def _event_state_snapshot() -> dict[str, object]:
    with EVENT_STATE_LOCK:
        snap = dict(_event_state)
    return {
        "enabled": bool(snap.get("enabled")),
        "verify_token_configured": bool(snap.get("verify_token_configured")),
        "encrypt_key_configured": bool(snap.get("encrypt_key_configured")),
        "debounce_sec": _sanitize_event_debounce(snap.get("debounce_sec")),
        "trigger_types": list(_normalize_event_trigger_types(snap.get("trigger_types"))),
        "pending": bool(snap.get("pending")),
        "last_received_at": _iso_from_ts(snap.get("last_received_at")),
        "last_event_type": snap.get("last_event_type"),
        "last_event_id": snap.get("last_event_id"),
        "last_challenge_at": _iso_from_ts(snap.get("last_challenge_at")),
        "last_trigger_requested_at": _iso_from_ts(snap.get("last_trigger_requested_at")),
        "last_triggered_at": _iso_from_ts(snap.get("last_triggered_at")),
        "last_result": snap.get("last_result"),
        "last_error": snap.get("last_error"),
        "received_count": _as_int(snap.get("received_count"), 0),
        "trigger_count": _as_int(snap.get("trigger_count"), 0),
        "duplicate_count": _as_int(snap.get("duplicate_count"), 0),
        "skipped_unmatched_count": _as_int(snap.get("skipped_unmatched_count"), 0),
        "skipped_debounce_count": _as_int(snap.get("skipped_debounce_count"), 0),
        "skipped_busy_count": _as_int(snap.get("skipped_busy_count"), 0),
        "skipped_pending_count": _as_int(snap.get("skipped_pending_count"), 0),
        "skipped_disabled_count": _as_int(snap.get("skipped_disabled_count"), 0),
    }


def _event_cleanup_recent_ids(now_ts: float) -> None:
    expired = [eid for eid, ts in _event_recent_ids.items() if now_ts - ts >= EVENT_DEDUP_TTL_SEC]
    for eid in expired:
        _event_recent_ids.pop(eid, None)


def _event_seen_recently(event_id: str, now_ts: float) -> bool:
    if not event_id:
        return False
    with EVENT_STATE_LOCK:
        _event_cleanup_recent_ids(now_ts)
        hit = event_id in _event_recent_ids
        if not hit:
            _event_recent_ids[event_id] = now_ts
        return hit


def _event_signature(timestamp: str, nonce: str, encrypt_key: str, body: str) -> str:
    raw = f"{timestamp}{nonce}{encrypt_key}{body}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _event_decrypt_payload(encrypt_text: str, encrypt_key: str) -> str:
    if AES is None:
        raise RuntimeError("event_decrypt_dependency_missing: install pycryptodome")
    buf = base64.b64decode(encrypt_text)
    if len(buf) < 16:
        raise RuntimeError("event_decrypt_failed: cipher_too_short")
    iv = buf[:16]
    data = buf[16:]
    if len(data) % 16 != 0:
        raise RuntimeError("event_decrypt_failed: invalid_block_size")
    key = hashlib.sha256(encrypt_key.encode("utf-8")).digest()
    plain_raw = AES.new(key, AES.MODE_CBC, iv).decrypt(data)
    plain_bytes = bytes(plain_raw)
    text = plain_bytes.decode("utf-8", errors="ignore")
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < 0 or end < start:
        raise RuntimeError("event_decrypt_failed: invalid_plaintext")
    return text[start : end + 1]


def _parse_feishu_event_request(raw_body: bytes, headers: dict[str, str], encrypt_key: str) -> dict[str, object]:
    body_text = raw_body.decode("utf-8", errors="replace")
    try:
        parsed = json.loads(body_text or "{}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"event_invalid_json: {e}") from e
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=400, detail="event_invalid_json: payload_not_object")

    payload = parsed
    if encrypt_key:
        encrypted = str(payload.get("encrypt") or "").strip()
        if not encrypted:
            raise HTTPException(status_code=400, detail="event_invalid_payload: encrypt_missing")
        try:
            payload = json.loads(_event_decrypt_payload(encrypted, encrypt_key))
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"event_decrypt_failed: {e}") from e
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="event_invalid_payload: decrypted_not_object")

    req_type = str(payload.get("type") or "").strip()
    challenge = str(payload.get("challenge") or "").strip()
    header_raw = payload.get("header")
    header: dict[str, object] = header_raw if isinstance(header_raw, dict) else {}
    token = str(payload.get("token") or header.get("token") or "").strip()
    event_id = str(header.get("event_id") or payload.get("uuid") or "").strip()
    event_type = str(header.get("event_type") or "").strip()
    if not event_type:
        event_obj = payload.get("event")
        if isinstance(event_obj, dict):
            event_type = str(event_obj.get("type") or "").strip()

    if not req_type:
        req_type = "event_callback" if event_type else "unknown"

    if encrypt_key and req_type != "url_verification":
        timestamp = headers.get("x-lark-request-timestamp", "")
        nonce = headers.get("x-lark-request-nonce", "")
        source_sign = headers.get("x-lark-signature", "")
        target_sign = _event_signature(timestamp, nonce, encrypt_key, body_text)
        if not source_sign or target_sign != source_sign:
            raise HTTPException(status_code=401, detail="event_signature_invalid")

    return {
        "req_type": req_type,
        "challenge": challenge,
        "token": token,
        "event_id": event_id,
        "event_type": event_type,
        "payload": payload,
    }


def _event_type_matched(event_type: str, patterns: list[str]) -> bool:
    if not event_type:
        return False
    for pattern in patterns:
        p = str(pattern or "").strip()
        if not p:
            continue
        if fnmatch.fnmatch(event_type, p):
            return True
    return False


def _run_event_sync_job(trigger_event_type: str, trigger_event_id: str, debounce_sec: int) -> None:
    logger = logging.getLogger("event_callback")
    acquired = False
    deadline = time.time() + EVENT_LOCK_WAIT_TIMEOUT_SEC
    while time.time() < deadline:
        if SYNC_RUN_LOCK.acquire(blocking=False):
            acquired = True
            break
        time.sleep(1)

    if not acquired:
        with EVENT_STATE_LOCK:
            _event_state["pending"] = False
            _event_state["last_result"] = "skipped_busy"
            _event_state["last_error"] = "sync_busy_timeout"
            _event_state["skipped_busy_count"] = _as_int(_event_state.get("skipped_busy_count"), 0) + 1
        logger.warning("event_sync_skipped_busy_timeout event_type=%s event_id=%s", trigger_event_type, trigger_event_id)
        return

    try:
        started_at = time.time()
        _event_state_update(last_triggered_at=started_at, last_result="running", last_error=None)
        summary = _run_sync_once_and_record("event_callback")
        errors = _as_int(summary.get("errors"), 0)
        fatal = str(summary.get("fatal_error") or "").strip()
        with EVENT_STATE_LOCK:
            _event_state["trigger_count"] = _as_int(_event_state.get("trigger_count"), 0) + 1
            _event_state["last_result"] = "warning" if (fatal or errors > 0) else "success"
            _event_state["last_error"] = fatal or (f"errors={errors}" if errors > 0 else None)
        logger.info(
            "event_sync_completed event_type=%s event_id=%s errors=%s uploaded=%s downloaded=%s debounce_sec=%s",
            trigger_event_type,
            trigger_event_id,
            errors,
            summary.get("uploaded", 0),
            summary.get("downloaded", 0),
            debounce_sec,
        )
    except Exception as e:
        _event_state_update(last_result="failed", last_error=str(e))
        logger.exception("event_sync_failed event_type=%s event_id=%s err=%s", trigger_event_type, trigger_event_id, e)
    finally:
        SYNC_RUN_LOCK.release()
        _event_state_update(pending=False)


async def _wait_stop_or_timeout(stop_event: asyncio.Event, timeout_sec: float) -> bool:
    if timeout_sec <= 0:
        return stop_event.is_set()
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=timeout_sec)
        return True
    except asyncio.TimeoutError:
        return False


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


def _build_feishu_client():
    cfg = load_config()
    init_db(cfg.database.path)
    client = FeishuClient(
        app_id=cfg.auth.app_id,
        app_secret=cfg.auth.app_secret,
        user_token_file=cfg.auth.user_token_file,
        timeout=int(cfg.auth.timeout_sec),
    )
    return cfg, client


def _event_runtime_settings(cfg) -> EventRuntimeSettings:
    enabled = bool(getattr(cfg.sync, "event_callback_enabled", False))
    verify_token = str(getattr(cfg.sync, "event_verify_token", "") or "").strip()
    encrypt_key = str(getattr(cfg.sync, "event_encrypt_key", "") or "").strip()
    debounce_sec = _sanitize_event_debounce(getattr(cfg.sync, "event_debounce_sec", 15))
    trigger_types = _normalize_event_trigger_types(getattr(cfg.sync, "event_trigger_types", EVENT_DEFAULT_TRIGGER_TYPES))
    return {
        "enabled": enabled,
        "verify_token": verify_token,
        "encrypt_key": encrypt_key,
        "debounce_sec": debounce_sec,
        "trigger_types": trigger_types,
    }


def _sync_event_state_from_config(cfg) -> EventRuntimeSettings:
    settings = _event_runtime_settings(cfg)
    _event_state_update(
        enabled=bool(settings["enabled"]),
        verify_token_configured=bool(settings["verify_token"]),
        encrypt_key_configured=bool(settings["encrypt_key"]),
        debounce_sec=int(settings["debounce_sec"]),
        trigger_types=list(settings["trigger_types"]),
    )
    return settings


def _build_readiness_payload() -> dict:
    checks: dict[str, bool] = {
        "config_load": False,
        "database_parent_ready": False,
        "log_parent_ready": False,
        "local_root_in_scope": False,
        "scheduler_running": False,
        "scheduler_enabled": False,
    }
    warnings: list[str] = []
    errors: list[str] = []
    scheduler = _scheduler_state_snapshot()
    checks["scheduler_running"] = bool(scheduler.get("running"))
    checks["scheduler_enabled"] = bool(scheduler.get("enabled"))

    cfg = None
    try:
        cfg = load_config()
        checks["config_load"] = True
    except Exception as e:
        errors.append(f"config_load_failed: {e}")

    if cfg is not None:
        checks["local_root_in_scope"] = is_local_root_in_scope(cfg.sync.local_root)
        if not checks["local_root_in_scope"]:
            warnings.append("local_root_out_of_scope")

        try:
            Path(cfg.database.path).parent.mkdir(parents=True, exist_ok=True)
            checks["database_parent_ready"] = True
        except Exception as e:
            errors.append(f"database_parent_unavailable: {e}")

        try:
            Path(cfg.logging.file).parent.mkdir(parents=True, exist_ok=True)
            checks["log_parent_ready"] = True
        except Exception as e:
            errors.append(f"log_parent_unavailable: {e}")

    if checks["scheduler_enabled"] and not checks["scheduler_running"]:
        warnings.append("scheduler_enabled_but_not_running")

    ok = checks["config_load"] and checks["database_parent_ready"] and checks["log_parent_ready"]
    return {
        "ok": ok,
        "checked_at": _now_iso(),
        "checks": checks,
        "warnings": warnings,
        "errors": errors,
        "scheduler": scheduler,
    }


def _run_sync_once_and_record(run_type: str) -> dict:
    _cfg, engine, local_root_locked, locked_from = _build_sync_engine()
    summary_raw = engine.run_once(run_type=run_type)
    summary: dict[str, object]
    if isinstance(summary_raw, dict):
        summary = dict(summary_raw)
    else:
        summary = {"fatal_error": "invalid_sync_summary"}
    if local_root_locked:
        summary["scope_warning"] = {
            "code": "local_root_scope_locked",
            "requested_local_root": str(locked_from or ""),
            "applied_local_root": FIXED_LOCAL_ROOT,
        }
    LAST_RUN_ONCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    LAST_RUN_ONCE_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    _append_run_history(summary)
    return summary


async def _scheduler_loop(stop_event: asyncio.Event) -> None:
    logger = logging.getLogger("scheduler")
    next_run_at_ts: float | None = None
    previous_effective_interval: int | None = None
    _scheduler_state_update(
        running=True,
        last_error=None,
        last_result=None,
    )
    logger.info("scheduler_started")

    try:
        while not stop_event.is_set():
            cfg = load_config()
            _sync_event_state_from_config(cfg)
            configured_interval = int(cfg.sync.poll_interval_sec or 0)
            effective_interval = _sanitize_poll_interval(configured_interval)
            enabled = configured_interval > 0

            _scheduler_state_update(
                enabled=enabled,
                configured_interval_sec=configured_interval,
                effective_interval_sec=effective_interval,
            )

            if not enabled:
                next_run_at_ts = None
                previous_effective_interval = None
                _scheduler_state_update(next_run_at=None)
                await _wait_stop_or_timeout(stop_event, SCHEDULER_POLL_GRANULARITY_SEC)
                continue

            now_ts = time.time()
            if next_run_at_ts is None:
                next_run_at_ts = now_ts + effective_interval
            elif previous_effective_interval is not None and previous_effective_interval != effective_interval:
                next_run_at_ts = now_ts + effective_interval
            previous_effective_interval = effective_interval
            _scheduler_state_update(next_run_at=next_run_at_ts)

            wait_sec = next_run_at_ts - now_ts
            if wait_sec > 0:
                await _wait_stop_or_timeout(stop_event, min(wait_sec, SCHEDULER_POLL_GRANULARITY_SEC))
                continue

            if not SYNC_RUN_LOCK.acquire(blocking=False):
                skipped = _as_int(_scheduler_state_snapshot().get("skipped_busy_count"), 0) + 1
                next_run_at_ts = time.time() + effective_interval
                _scheduler_state_update(
                    skipped_busy_count=skipped,
                    last_finished_at=time.time(),
                    last_result="skipped_busy",
                    last_error="sync_busy",
                    next_run_at=next_run_at_ts,
                )
                logger.warning("scheduled_sync_skipped sync_busy")
                continue

            started_ts = time.time()
            _scheduler_state_update(last_started_at=started_ts, last_result="running", last_error=None)
            try:
                summary = await asyncio.to_thread(_run_sync_once_and_record, "scheduled")
                errors = _as_int(summary.get("errors", 0), 0)
                fatal = summary.get("fatal_error")
                run_count = _as_int(_scheduler_state_snapshot().get("run_count"), 0) + 1
                _scheduler_state_update(
                    last_finished_at=time.time(),
                    last_result="warning" if (fatal or errors > 0) else "success",
                    last_error=str(fatal or "") if fatal else (f"errors={errors}" if errors > 0 else None),
                    run_count=run_count,
                )
                logger.info(
                    "scheduled_sync_completed errors=%s uploaded=%s downloaded=%s renamed=%s",
                    errors,
                    summary.get("uploaded", 0),
                    summary.get("downloaded", 0),
                    summary.get("renamed", 0),
                )
            except Exception as e:
                run_count = _as_int(_scheduler_state_snapshot().get("run_count"), 0) + 1
                _scheduler_state_update(
                    last_finished_at=time.time(),
                    last_result="failed",
                    last_error=str(e),
                    run_count=run_count,
                )
                logger.exception("scheduled_sync_failed: %s", e)
            finally:
                SYNC_RUN_LOCK.release()
                next_run_at_ts = time.time() + effective_interval
                _scheduler_state_update(next_run_at=next_run_at_ts)
    finally:
        _scheduler_state_update(running=False, next_run_at=None)
        logger.info("scheduler_stopped")


def start_scheduler() -> None:
    global _scheduler_task, _scheduler_stop_event
    if _scheduler_task and not _scheduler_task.done():
        return

    _scheduler_stop_event = asyncio.Event()
    _scheduler_task = asyncio.create_task(_scheduler_loop(_scheduler_stop_event), name="localfilesync_scheduler")


async def stop_scheduler() -> None:
    global _scheduler_task, _scheduler_stop_event
    if _scheduler_stop_event is not None:
        _scheduler_stop_event.set()

    if _scheduler_task is not None:
        try:
            await _scheduler_task
        except Exception:
            logging.getLogger("scheduler").exception("scheduler_stop_error")

    _scheduler_task = None
    _scheduler_stop_event = None
    _scheduler_state_update(running=False, next_run_at=None)


def _safe_feishu_item_name(item: dict) -> str:
    raw = (item.get("name") or item.get("title") or item.get("token") or "").strip()
    return raw or "(unnamed)"


def _safe_feishu_item_size(item: dict) -> int:
    try:
        return int(item.get("size") or 0)
    except Exception:
        return 0


@router.get("/healthz")
def healthz():
    return {
        "ok": True,
        "status": "alive",
        "checked_at": _now_iso(),
    }


@router.get("/readyz")
def readyz():
    payload = _build_readiness_payload()
    return JSONResponse(status_code=200 if payload["ok"] else 503, content=payload)


@router.get("/config")
def get_config():
    cfg = load_config()
    event_settings = _sync_event_state_from_config(cfg)
    effective_interval = _sanitize_poll_interval(cfg.sync.poll_interval_sec)
    return {
        **cfg.model_dump(),
        "_scope": {
            "fixed_local_root": FIXED_LOCAL_ROOT,
            "configured_local_root": cfg.sync.local_root,
            "out_of_scope": not is_local_root_in_scope(cfg.sync.local_root),
        },
        "_scheduler": {
            "configured_poll_interval_sec": int(cfg.sync.poll_interval_sec or 0),
            "effective_poll_interval_sec": effective_interval,
            "auto_sync_enabled": int(cfg.sync.poll_interval_sec or 0) > 0,
        },
        "_event": {
            "enabled": bool(event_settings["enabled"]),
            "verify_token_configured": bool(event_settings["verify_token"]),
            "encrypt_key_configured": bool(event_settings["encrypt_key"]),
            "debounce_sec": int(event_settings["debounce_sec"]),
            "trigger_types": list(event_settings["trigger_types"]),
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

    try:
        cfg2 = cfg.model_validate(merged)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"invalid_config: {e}")
    local_root_locked, locked_from = enforce_local_root_scope(cfg2)
    save_config(cfg2)
    warnings: list[dict[str, object]] = []
    if local_root_locked:
        warnings.append(
            {
                "code": "local_root_scope_locked",
                "requested_local_root": str(locked_from or requested_local_root or ""),
                "applied_local_root": FIXED_LOCAL_ROOT,
            }
        )
    configured_interval = int(cfg2.sync.poll_interval_sec or 0)
    effective_interval = _sanitize_poll_interval(configured_interval)
    _scheduler_state_update(
        enabled=configured_interval > 0,
        configured_interval_sec=configured_interval,
        effective_interval_sec=effective_interval,
    )
    event_settings = _sync_event_state_from_config(cfg2)
    if bool(event_settings["enabled"]) and not bool(event_settings["verify_token"]):
        warnings.append(
            {
                "code": "event_verify_token_missing",
                "message": "event_callback_enabled=true but sync.event_verify_token is empty",
            }
        )
    if bool(event_settings["enabled"]) and bool(event_settings["encrypt_key"]) and AES is None:
        warnings.append(
            {
                "code": "event_encrypt_dependency_missing",
                "message": "event_encrypt_key configured but pycryptodome is not installed",
            }
        )
    if configured_interval > 0 and configured_interval != effective_interval:
        warnings.append(
            {
                "code": "poll_interval_clamped",
                "configured_poll_interval_sec": configured_interval,
                "effective_poll_interval_sec": effective_interval,
            }
        )
    return {"ok": True, "warnings": warnings}


@router.get("/drive/tree")
def drive_tree(depth: int = 4, include_recycle_bin: bool = False):
    depth = min(max(int(depth), 1), 8)
    cfg, client = _build_feishu_client()

    token, token_type = client.get_access_token(priority=("user", "tenant"))
    if not token:
        return {
            "ok": False,
            "checked_at": _now_iso(),
            "error": "no_available_token",
            "token_type": None,
            "configured_folder_token": cfg.sync.remote_folder_token or "",
        }

    root_token = cfg.sync.remote_folder_token or client.get_root_folder_token()
    recycle_bin_name = (cfg.sync.remote_recycle_bin or "").strip()
    stats = {"folders": 0, "files": 0, "truncated_nodes": 0}
    visited: set[str] = {root_token}

    def walk(folder_token: str, folder_name: str, folder_path: str, level: int) -> dict[str, Any]:
        node: dict[str, Any] = {
            "type": "folder",
            "name": folder_name,
            "token": folder_token,
            "path": folder_path,
            "children": [],
        }
        if level >= depth:
            node["truncated"] = True
            stats["truncated_nodes"] += 1
            return node

        children = client.list_folder_once(folder_token)
        normalized: list[tuple[int, str, dict[str, Any]]] = []
        for item in children:
            item_type = item.get("type") or "file"
            name = _safe_feishu_item_name(item)
            order = 0 if item_type == "folder" else 1
            normalized.append((order, name.lower(), item))
        normalized.sort(key=lambda x: (x[0], x[1]))

        for _order, _name_key, item in normalized:
            item_type = item.get("type") or "file"
            name = _safe_feishu_item_name(item)
            item_token = item.get("token") or ""
            path = f"{folder_path}/{name}" if folder_path else name

            if (
                not include_recycle_bin
                and recycle_bin_name
                and item_type == "folder"
                and name == recycle_bin_name
            ):
                continue

            if item_type == "folder":
                stats["folders"] += 1
                folder_node: dict[str, Any] = {
                    "type": "folder",
                    "name": name,
                    "token": item_token,
                    "path": path,
                    "children": [],
                }
                if not item_token:
                    folder_node["invalid"] = True
                    node["children"].append(folder_node)
                    continue
                if item_token in visited:
                    folder_node["cycle"] = True
                    node["children"].append(folder_node)
                    continue

                visited.add(item_token)
                if level + 1 >= depth:
                    folder_node["truncated"] = True
                    stats["truncated_nodes"] += 1
                    node["children"].append(folder_node)
                    continue

                nested = walk(item_token, name, path, level + 1)
                folder_node["children"] = nested.get("children", [])
                if nested.get("truncated"):
                    folder_node["truncated"] = True
                node["children"].append(folder_node)
                continue

            stats["files"] += 1
            node["children"].append(
                {
                    "type": "file",
                    "name": name,
                    "token": item_token,
                    "path": path,
                    "size": _safe_feishu_item_size(item),
                    "modified_time": item.get("modified_time") or item.get("modified_at") or "",
                }
            )

        return node

    tree = walk(root_token, "drive_root", "", 0)
    return {
        "ok": True,
        "checked_at": _now_iso(),
        "depth": depth,
        "include_recycle_bin": include_recycle_bin,
        "token_type": token_type,
        "configured_folder_token": cfg.sync.remote_folder_token or "",
        "root_folder_token": root_token,
        "stats": stats,
        "tree": tree,
    }


@router.get("/auth/url")
def auth_url(redirect_uri: str = "https://open.feishu.cn/connect/confirm_success"):
    try:
        cfg, client = _build_feishu_client()
        state = secrets.token_hex(16)
        url = client.create_oauth_authorize_url(redirect_uri=redirect_uri, state=state)
        AUTH_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        AUTH_STATE_PATH.write_text(state, encoding="utf-8")
        return {
            "ok": True,
            "auth_url": url,
            "state": state,
            "state_path": str(AUTH_STATE_PATH),
            "redirect_uri": redirect_uri,
            "token_file": cfg.auth.user_token_file,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/auth/exchange")
def auth_exchange(payload: dict):
    try:
        code = str(payload.get("code", "")).strip()
        if not code:
            return {"ok": False, "error": "oauth_code_missing"}
        cfg, client = _build_feishu_client()
        token_data = client.exchange_code_for_user_token(code)
        return {
            "ok": True,
            "saved_to": cfg.auth.user_token_file,
            "token_type": token_data.get("token_type"),
            "expires_in": token_data.get("expires_in"),
            "refresh_expires_in": token_data.get("refresh_expires_in"),
            "created_at": token_data.get("created_at"),
            "has_access_token": bool(token_data.get("access_token")),
            "has_refresh_token": bool(token_data.get("refresh_token")),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/auth/refresh")
def auth_refresh(force: bool = True):
    try:
        cfg, client = _build_feishu_client()
        token_data = client.refresh_user_access_token(force=force)
        return {
            "ok": True,
            "saved_to": cfg.auth.user_token_file,
            "token_type": token_data.get("token_type"),
            "expires_in": token_data.get("expires_in"),
            "refresh_expires_in": token_data.get("refresh_expires_in"),
            "created_at": token_data.get("created_at"),
            "has_access_token": bool(token_data.get("access_token")),
            "has_refresh_token": bool(token_data.get("refresh_token")),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.get("/logs")
def get_logs(n: int = 200, level: str | None = None, module: str | None = None):
    cfg = load_config()
    payload = build_log_tail_payload(
        cfg.logging.file,
        n=n,
        level=level,
        module=module,
    )
    return payload


@router.get("/history")
def get_history(limit: int = 50):
    limit_sanitized = min(max(int(limit), 1), 500)
    items = _read_run_history(limit=limit_sanitized)
    return {
        "path": str(RUN_HISTORY_PATH),
        "limit": limit_sanitized,
        "count": len(items),
        "items": items,
    }


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


@router.get("/status/scheduler")
def scheduler_status():
    return {
        "ok": True,
        "checked_at": _now_iso(),
        **_scheduler_state_snapshot(),
    }


@router.get("/status/event-callback")
def event_callback_status():
    cfg = load_config()
    _sync_event_state_from_config(cfg)
    return {
        "ok": True,
        "checked_at": _now_iso(),
        **_event_state_snapshot(),
    }


@router.get("/status/run-once")
def last_run_once_status():
    summary, source, parse_error = _load_latest_run_summary()
    out: dict[str, Any] = {
        "exists": LAST_RUN_ONCE_PATH.exists(),
        "path": str(LAST_RUN_ONCE_PATH),
        "summary": summary,
        "summary_source": source,
    }
    if parse_error:
        out["error"] = parse_error
    return out


@router.get("/status/feishu")
def feishu_status():
    cfg = load_config()
    user_token_file = cfg.auth.user_token_file
    token_file_path = Path(user_token_file).expanduser() if user_token_file else None

    status: dict[str, Any] = {
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


@router.post("/events/feishu")
async def feishu_event_callback(request: Request, background: BackgroundTasks):
    cfg = load_config()
    event_settings = _sync_event_state_from_config(cfg)
    verify_token = str(event_settings["verify_token"])
    encrypt_key = str(event_settings["encrypt_key"])
    debounce_sec = int(event_settings["debounce_sec"])
    trigger_types = list(event_settings["trigger_types"])
    enabled = bool(event_settings["enabled"])

    raw_body = await request.body()
    now_ts = time.time()
    headers = {k.lower(): v for k, v in request.headers.items()}
    parsed = _parse_feishu_event_request(raw_body, headers, encrypt_key=encrypt_key)

    req_type = str(parsed.get("req_type") or "")
    challenge = str(parsed.get("challenge") or "")
    token = str(parsed.get("token") or "")
    event_type = str(parsed.get("event_type") or "")
    event_id = str(parsed.get("event_id") or "")

    if verify_token and token != verify_token:
        raise HTTPException(status_code=401, detail="event_token_invalid")

    if req_type == "url_verification":
        _event_state_update(
            last_challenge_at=now_ts,
            last_received_at=now_ts,
            last_event_type=event_type or "url_verification",
            last_event_id=event_id,
            last_result="challenge_ok",
            last_error=None,
        )
        return {"challenge": challenge}

    with EVENT_STATE_LOCK:
        _event_state["received_count"] = _as_int(_event_state.get("received_count"), 0) + 1
        _event_state["last_received_at"] = now_ts
        _event_state["last_event_type"] = event_type
        _event_state["last_event_id"] = event_id

    if not enabled:
        with EVENT_STATE_LOCK:
            _event_state["skipped_disabled_count"] = _as_int(_event_state.get("skipped_disabled_count"), 0) + 1
            _event_state["last_result"] = "disabled"
            _event_state["last_error"] = None
        return {"msg": "success", "queued": False, "reason": "event_callback_disabled"}

    if _event_seen_recently(event_id, now_ts):
        with EVENT_STATE_LOCK:
            _event_state["duplicate_count"] = _as_int(_event_state.get("duplicate_count"), 0) + 1
            _event_state["last_result"] = "duplicate"
            _event_state["last_error"] = None
        return {"msg": "success", "queued": False, "reason": "duplicate_event"}

    if not _event_type_matched(event_type, trigger_types):
        with EVENT_STATE_LOCK:
            _event_state["skipped_unmatched_count"] = _as_int(_event_state.get("skipped_unmatched_count"), 0) + 1
            _event_state["last_result"] = "ignored"
            _event_state["last_error"] = f"unmatched_event_type:{event_type}"
        return {"msg": "success", "queued": False, "reason": "unmatched_event_type"}

    with EVENT_STATE_LOCK:
        last_requested = _as_float(_event_state.get("last_trigger_requested_at"))
        if debounce_sec > 0 and last_requested is not None and now_ts - last_requested < debounce_sec:
            _event_state["skipped_debounce_count"] = _as_int(_event_state.get("skipped_debounce_count"), 0) + 1
            _event_state["last_result"] = "debounced"
            _event_state["last_error"] = None
            return {"msg": "success", "queued": False, "reason": "debounced"}
        if bool(_event_state.get("pending")):
            _event_state["skipped_pending_count"] = _as_int(_event_state.get("skipped_pending_count"), 0) + 1
            _event_state["last_result"] = "pending"
            _event_state["last_error"] = None
            return {"msg": "success", "queued": False, "reason": "pending_job"}
        _event_state["pending"] = True
        _event_state["last_trigger_requested_at"] = now_ts
        _event_state["last_result"] = "queued"
        _event_state["last_error"] = None

    background.add_task(_run_event_sync_job, event_type, event_id, debounce_sec)
    return {"msg": "success", "queued": True, "event_type": event_type, "event_id": event_id}


@router.post("/actions/run-once")
def run_once():
    """Run one legacy sync now and return summary."""

    from app.core.last_cmd import record

    record("POST /api/actions/run-once (trigger legacy sync)")
    if not SYNC_RUN_LOCK.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="sync_busy")
    try:
        summary = _run_sync_once_and_record("manual_web")
    finally:
        SYNC_RUN_LOCK.release()
    return summary


@router.post("/actions/clear-last-run")
def clear_last_run():
    """Clear error marker on latest run summary while keeping the record."""
    cleared = False
    try:
        summary, source, parse_error = _load_latest_run_summary()
        if summary and isinstance(summary, dict):
            normalized = dict(summary)
            has_error = bool(normalized.get("fatal_error")) or _as_int(normalized.get("errors", 0), 0) > 0
            if has_error:
                normalized["errors"] = 0
                normalized.pop("fatal_error", None)
                normalized["error_cleared_at"] = _now_iso()
                normalized["error_cleared_by"] = "web_clear_last_run"
                cleared = True
            LAST_RUN_ONCE_PATH.parent.mkdir(parents=True, exist_ok=True)
            LAST_RUN_ONCE_PATH.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
        return {
            "ok": True,
            "cleared": cleared,
            "path": str(LAST_RUN_ONCE_PATH),
            "summary_source": source,
            "summary_exists": bool(summary),
            "parse_error": parse_error,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"clear_last_run_failed: {e}")
