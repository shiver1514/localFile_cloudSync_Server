from __future__ import annotations

import json
import logging
import secrets
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from app.core.config import (
    AUTH_STATE_PATH,
    DEFAULT_CONFIG_PATH,
    FIXED_LOCAL_ROOT,
    LAST_RUN_ONCE_PATH,
    RUNTIME_DIR,
    RUN_HISTORY_PATH,
    enforce_local_root_scope,
    is_local_root_in_scope,
    load_config,
    save_config,
)
from app.core.log_tail import build_log_tail_payload
from app.providers.feishu_legacy import FeishuClient, SyncEngine
from app.providers.feishu_legacy.db import init_db
from app.providers.feishu_legacy.sync_engine import scan_local_dirs, scan_local_files

app = typer.Typer(add_completion=False)
console = Console()


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


def _service_status_summary(unit: str = "localfile-cloudsync.service") -> str:
    try:
        probe = _run_systemctl_user(["--version"], timeout_sec=3)
        if probe.returncode != 0:
            return "systemd_unavailable"

        show = _run_systemctl_user(
            ["show", unit, "--property", "ActiveState,SubState,MainPID,UnitFileState"],
            timeout_sec=4,
        )
        if show.returncode != 0:
            return (show.stderr or show.stdout or "service_status_unavailable").strip()

        props = _parse_systemctl_show(show.stdout or "")
        active = props.get("ActiveState") or "unknown"
        sub = props.get("SubState") or "unknown"
        unit_file = props.get("UnitFileState") or "unknown"
        main_pid = props.get("MainPID") or "-"
        return f"{active}/{sub} unit={unit_file} pid={main_pid}"
    except Exception as e:
        return f"service_status_error: {e}"


def _append_run_history(summary: dict) -> None:
    RUN_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with RUN_HISTORY_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(summary, ensure_ascii=False))
        f.write("\n")


def _build_sync_engine() -> tuple:
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


@app.command("config-show")
def config_show(path: Path = DEFAULT_CONFIG_PATH):
    """Show current config.yaml."""
    from app.core.last_cmd import record

    record("localfilesync-cli config-show")
    cfg = load_config(path)
    print(json.dumps(cfg.model_dump(), ensure_ascii=False, indent=2))


@app.command("config-set-web")
def config_set_web(bind: str = typer.Option(..., "--bind"), port: int = typer.Option(8765, "--port")):
    """Set Web UI bind host/port."""
    cfg = load_config()
    cfg.web_bind_host = bind
    cfg.web_port = port
    save_config(cfg)
    print(f"OK: web_bind_host={bind} web_port={port}")


@app.command("config-set-auth")
def config_set_auth(
    app_id: str = typer.Option(..., "--app-id", help="Feishu app_id"),
    app_secret: str = typer.Option(..., "--app-secret", help="Feishu app_secret"),
    user_token_file: str = typer.Option(
        str(RUNTIME_DIR / "user_tokens.json"),
        "--user-token-file",
        help="Path for storing user tokens",
    ),
):
    """Set Feishu auth config for OAuth/token flow."""
    cfg = load_config()
    cfg.auth.app_id = app_id
    cfg.auth.app_secret = app_secret
    cfg.auth.user_token_file = user_token_file
    save_config(cfg)
    print(
        json.dumps(
            {
                "ok": True,
                "app_id_set": bool(cfg.auth.app_id),
                "app_secret_set": bool(cfg.auth.app_secret),
                "user_token_file": cfg.auth.user_token_file,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


@app.command()
def status():
    """Show runtime and readiness summary."""
    cfg = load_config()
    token_path = Path(cfg.auth.user_token_file).expanduser() if cfg.auth.user_token_file else None
    token_exists = bool(token_path and token_path.exists())
    local_root_in_scope = is_local_root_in_scope(cfg.sync.local_root)
    service_summary = _service_status_summary()

    table = Table(title="localFile_cloudSync_Server status")
    table.add_column("Key")
    table.add_column("Value")
    table.add_row("config", str(DEFAULT_CONFIG_PATH))
    table.add_row("local_root", cfg.sync.local_root)
    table.add_row("local_root_in_scope", "yes" if local_root_in_scope else "no")
    table.add_row("token_file", str(token_path) if token_path else "(unset)")
    table.add_row("token_file_exists", "yes" if token_exists else "no")
    poll_interval = int(cfg.sync.poll_interval_sec or 0)
    table.add_row("auto_sync", "on" if poll_interval > 0 else "off")
    table.add_row("poll_interval_sec", str(poll_interval))
    table.add_row("service", service_summary)
    table.add_row("db", cfg.database.path)
    table.add_row("log", cfg.logging.file)
    table.add_row("web", f"http://{cfg.web_bind_host}:{cfg.web_port}")
    console.print(table)


@app.command("config-validate")
def config_validate(
    path: Path = DEFAULT_CONFIG_PATH,
    strict: bool = typer.Option(False, "--strict", help="Return non-zero when validation fails."),
):
    """Validate config and runtime prerequisites."""
    out: dict[str, Any] = {
        "ok": True,
        "checked_at": _now_iso(),
        "config_path": str(path),
        "checks": {
            "config_exists": path.exists(),
            "app_id_configured": False,
            "app_secret_configured": False,
            "user_token_file_configured": False,
            "user_token_file_exists": False,
            "local_root_in_scope": False,
            "web_bind_host_configured": False,
            "web_port_valid": False,
            "poll_interval_valid": False,
            "database_parent_ready": False,
            "log_parent_ready": False,
        },
        "warnings": [],
        "errors": [],
    }

    try:
        cfg = load_config(path)
    except Exception as e:
        out["ok"] = False
        out["errors"].append(f"load_config_failed: {e}")
        print(json.dumps(out, ensure_ascii=False, indent=2))
        if strict:
            raise typer.Exit(2)
        return

    out["checks"]["app_id_configured"] = bool(cfg.auth.app_id)
    out["checks"]["app_secret_configured"] = bool(cfg.auth.app_secret)
    out["checks"]["user_token_file_configured"] = bool(cfg.auth.user_token_file)

    if cfg.auth.user_token_file:
        token_path = Path(cfg.auth.user_token_file).expanduser()
        out["checks"]["user_token_file_exists"] = token_path.exists()
        if not token_path.exists():
            out["warnings"].append(f"user_token_file_missing: {token_path}")

    out["checks"]["local_root_in_scope"] = is_local_root_in_scope(cfg.sync.local_root)
    if not out["checks"]["local_root_in_scope"]:
        out["warnings"].append(
            f"local_root_out_of_scope: configured={cfg.sync.local_root} fixed={FIXED_LOCAL_ROOT}"
        )

    bind_host = str(cfg.web_bind_host or "").strip()
    out["checks"]["web_bind_host_configured"] = bool(bind_host)
    if not out["checks"]["web_bind_host_configured"]:
        out["errors"].append("web_bind_host_missing")

    port = int(cfg.web_port)
    out["checks"]["web_port_valid"] = 1 <= port <= 65535
    if not out["checks"]["web_port_valid"]:
        out["errors"].append(f"web_port_out_of_range: {port}")

    poll_interval = int(cfg.sync.poll_interval_sec or 0)
    out["checks"]["poll_interval_valid"] = 0 <= poll_interval <= 86400
    if not out["checks"]["poll_interval_valid"]:
        out["errors"].append(f"poll_interval_out_of_range: {poll_interval}")
    elif 0 < poll_interval < 10:
        out["warnings"].append(f"poll_interval_too_short: {poll_interval} (<10 may cause rate/risk)")

    try:
        Path(cfg.database.path).parent.mkdir(parents=True, exist_ok=True)
        out["checks"]["database_parent_ready"] = True
    except Exception as e:
        out["errors"].append(f"database_parent_unavailable: {e}")

    try:
        Path(cfg.logging.file).parent.mkdir(parents=True, exist_ok=True)
        out["checks"]["log_parent_ready"] = True
    except Exception as e:
        out["errors"].append(f"log_parent_unavailable: {e}")

    if not out["checks"]["app_id_configured"] or not out["checks"]["app_secret_configured"]:
        out["warnings"].append("auth_incomplete: app_id/app_secret not fully configured")

    out["ok"] = len(out["errors"]) == 0
    print(json.dumps(out, ensure_ascii=False, indent=2))
    if strict and not out["ok"]:
        raise typer.Exit(2)


@app.command("auth-url")
def auth_url(
    redirect_uri: str = typer.Option(
        "https://open.feishu.cn/connect/confirm_success",
        "--redirect-uri",
        help="OAuth redirect URI configured in Feishu app.",
    ),
):
    """Generate Feishu OAuth URL for user token authorization."""
    try:
        cfg, client = _build_feishu_client()
        state = secrets.token_hex(16)
        url = client.create_oauth_authorize_url(redirect_uri=redirect_uri, state=state)
        AUTH_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        AUTH_STATE_PATH.write_text(state, encoding="utf-8")
        print(
            json.dumps(
                {
                    "ok": True,
                    "auth_url": url,
                    "state": state,
                    "state_path": str(AUTH_STATE_PATH),
                    "redirect_uri": redirect_uri,
                    "token_file": cfg.auth.user_token_file,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False, indent=2))
        raise typer.Exit(2)


@app.command("auth-exchange")
def auth_exchange(
    code: str = typer.Option(..., "--code", help="OAuth code returned by Feishu."),
):
    """Exchange OAuth code for user token and save it to user_token_file."""
    try:
        cfg, client = _build_feishu_client()
        token_data = client.exchange_code_for_user_token(code)
        print(
            json.dumps(
                {
                    "ok": True,
                    "saved_to": cfg.auth.user_token_file,
                    "token_type": token_data.get("token_type"),
                    "expires_in": token_data.get("expires_in"),
                    "refresh_expires_in": token_data.get("refresh_expires_in"),
                    "created_at": token_data.get("created_at"),
                    "has_access_token": bool(token_data.get("access_token")),
                    "has_refresh_token": bool(token_data.get("refresh_token")),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False, indent=2))
        raise typer.Exit(2)


@app.command("auth-refresh")
def auth_refresh(
    force: bool = typer.Option(
        True,
        "--force/--no-force",
        help="Force refresh even if current access token still looks valid.",
    ),
):
    """Refresh user access token using refresh_token."""
    try:
        cfg, client = _build_feishu_client()
        token_data = client.refresh_user_access_token(force=force)
        print(
            json.dumps(
                {
                    "ok": True,
                    "saved_to": cfg.auth.user_token_file,
                    "token_type": token_data.get("token_type"),
                    "expires_in": token_data.get("expires_in"),
                    "refresh_expires_in": token_data.get("refresh_expires_in"),
                    "created_at": token_data.get("created_at"),
                    "has_access_token": bool(token_data.get("access_token")),
                    "has_refresh_token": bool(token_data.get("refresh_token")),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False, indent=2))
        raise typer.Exit(2)


@app.command("service-restart")
def service_restart():
    """Restart the Web UI service."""
    subprocess.check_call(["systemctl", "--user", "restart", "localfile-cloudsync.service"])
    print("OK")


@app.command("logs-tail")
def logs_tail(
    n: int = typer.Option(200, "--n", min=1),
    level: str | None = typer.Option(None, "--level", help="Filter by log level (e.g. INFO)."),
    module: str | None = typer.Option(None, "--module", help="Filter by logger/module name."),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON."),
):
    """Tail service log file."""
    cfg = load_config()
    payload = build_log_tail_payload(
        cfg.logging.file,
        n=n,
        level=level,
        module=module,
    )
    if json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    print(payload.get("tail", ""))


@app.command("service-status")
def service_status():
    """Show systemd --user service status."""
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
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return

    if probe.returncode != 0:
        out["error"] = (probe.stderr or probe.stdout or "systemctl_unavailable").strip()
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return

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

    print(json.dumps(out, ensure_ascii=False, indent=2))


@app.command("run-once")
def run_once(
    dry_run: bool = typer.Option(False, "--dry-run", help="Do local preflight only, no remote calls."),
    run_type: str = typer.Option("manual_cli", "--run-type", help="sync run_type label."),
):
    """Run one sync and print summary JSON."""
    from app.core.last_cmd import record

    cmd = "localfilesync-cli run-once --dry-run" if dry_run else "localfilesync-cli run-once"
    record(cmd)

    if dry_run:
        cfg = load_config()
        local_root_locked, requested_local_root = enforce_local_root_scope(cfg)
        init_db(cfg.database.path)

        local_root = Path(cfg.sync.local_root)
        local_root.mkdir(parents=True, exist_ok=True)
        local_dirs = scan_local_dirs(
            str(local_root),
            cfg.sync.exclude_dirs,
            exclude_hidden_dirs=bool(getattr(cfg.sync, "exclude_hidden_dirs", True)),
        )
        local_files = scan_local_files(
            str(local_root),
            cfg.sync.exclude_dirs,
            exclude_hidden_dirs=bool(getattr(cfg.sync, "exclude_hidden_dirs", True)),
            exclude_hidden_files=bool(getattr(cfg.sync, "exclude_hidden_files", True)),
        )

        summary = {
            "dry_run": True,
            "run_type": run_type,
            "checked_at": _now_iso(),
            "local_root": str(local_root),
            "remote_root_token": "",
            "local_dirs": len(local_dirs),
            "local_total": len(local_files),
            "remote_total": None,
            "uploaded": 0,
            "downloaded": 0,
            "renamed": 0,
            "conflicts": 0,
            "remote_soft_deleted": 0,
            "local_soft_deleted": 0,
            "retry_success": 0,
            "retry_failed": 0,
            "errors": 0,
            "notes": ["dry_run_skips_remote_operations"],
        }
        if local_root_locked:
            summary["scope_warning"] = {
                "code": "local_root_scope_locked",
                "requested_local_root": str(requested_local_root or ""),
                "applied_local_root": FIXED_LOCAL_ROOT,
            }
        LAST_RUN_ONCE_PATH.parent.mkdir(parents=True, exist_ok=True)
        LAST_RUN_ONCE_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        _append_run_history(summary)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    _cfg, engine, local_root_locked, requested_local_root = _build_sync_engine()
    summary = engine.run_once(run_type=run_type)
    if local_root_locked:
        summary["scope_warning"] = {
            "code": "local_root_scope_locked",
            "requested_local_root": str(requested_local_root or ""),
            "applied_local_root": FIXED_LOCAL_ROOT,
        }
    LAST_RUN_ONCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    LAST_RUN_ONCE_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    _append_run_history(summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if summary.get("fatal_error") or int(summary.get("errors", 0)) > 0:
        raise typer.Exit(2)


def main():
    app()


if __name__ == "__main__":
    main()
