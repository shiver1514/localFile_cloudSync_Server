#!/usr/bin/env python3
import argparse
import json
import logging
import time
from datetime import datetime
from pathlib import Path

import yaml

from db import get_conn, init_db
from feishu_client import FeishuClient
from sync_engine import SyncEngine

ROOT = Path(__file__).resolve().parent
CFG_PATH = ROOT / "config.yaml"


def load_cfg():
    return yaml.safe_load(CFG_PATH.read_text(encoding="utf-8"))


def init_logger(log_file: str, level: str):
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=log_file,
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(message)s",
    )


def append_jsonl(log_dir: str, item: dict):
    day = datetime.now().strftime("%Y%m%d")
    path = Path(log_dir) / f"sync-{day}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(item, ensure_ascii=False) + "\n")


def make_log_func(db_path: str, log_dir: str):
    def _log(level: str, module: str, message: str, detail: str = None):
        level = (level or "INFO").upper()
        logging.log(getattr(logging, level, logging.INFO), f"[{module}] {message} {detail or ''}".strip())

        conn = get_conn(db_path)
        conn.execute(
            "INSERT INTO logs(level,module,message,detail) VALUES (?,?,?,?)",
            (level, module, message, detail),
        )
        conn.commit()
        conn.close()

        append_jsonl(
            log_dir,
            {
                "time": datetime.now().isoformat(timespec="seconds"),
                "level": level,
                "module": module,
                "message": message,
                "detail": detail,
            },
        )

    return _log


def _load_dotenv(dotenv_path: Path):
    values = {}
    if not dotenv_path.exists() or not dotenv_path.is_file():
        return values

    for line in dotenv_path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, val = raw.split("=", 1)
        values[key.strip()] = val.strip().strip('"').strip("'")
    return values


def build_client(cfg: dict):
    auth = cfg.get("auth", {})
    app_id = auth.get("app_id", "")
    app_secret = auth.get("app_secret", "")
    user_token_file = auth.get("user_token_file", "")

    if not app_id or not app_secret:
        env_file = auth.get("env_file")
        if env_file:
            env_path = Path(env_file)
        elif user_token_file:
            env_path = Path(user_token_file).parent / ".env"
        else:
            env_path = None

        if env_path:
            env_values = _load_dotenv(env_path)
            app_id = app_id or env_values.get("FEISHU_APP_ID", "")
            app_secret = app_secret or env_values.get("FEISHU_APP_SECRET", "")

    return FeishuClient(
        app_id=app_id,
        app_secret=app_secret,
        user_token_file=user_token_file,
        timeout=int(auth.get("timeout_sec", 30)),
    )


def build_engine(cfg: dict, db_path: str, log_func):
    client = build_client(cfg)
    return SyncEngine(cfg=cfg, db_path=db_path, client=client, log_func=log_func)


def cmd_run_once(cfg: dict, db_path: str, log_dir: str, run_type: str = "manual"):
    log_func = make_log_func(db_path, log_dir)
    engine = build_engine(cfg, db_path, log_func)

    # Always refresh the root index before syncing.
    try:
        from index_generator import write_index_file

        docs_db_path = str(Path(cfg.get("sync", {}).get("local_root") or str(engine.local_root)) / ".local_state" / "docs.db")
        local_root = cfg.get("sync", {}).get("local_root") or str(engine.local_root)
        write_index_file(db_path=docs_db_path, local_root=local_root)
    except Exception as e:
        log_func("WARN", "index", "index_generate_failed", str(e))

    summary = engine.run_once(run_type=run_type)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary.get("errors", 0) == 0 and not summary.get("fatal_error") else 2


def cmd_status(db_path: str):
    conn = get_conn(db_path)

    last_run = conn.execute(
        "SELECT id,run_type,status,started_at,finished_at,summary_json FROM sync_runs ORDER BY id DESC LIMIT 1"
    ).fetchone()
    retry_count = conn.execute("SELECT COUNT(1) AS n FROM retry_queue").fetchone()["n"]
    conflict_count = conn.execute(
        "SELECT COUNT(1) AS n FROM file_mappings WHERE conflict=1 AND status!='deleted'"
    ).fetchone()["n"]
    active_mappings = conn.execute(
        "SELECT COUNT(1) AS n FROM file_mappings WHERE status='active'"
    ).fetchone()["n"]

    conn.close()

    out = {
        "ok": True,
        "time": datetime.now().isoformat(timespec="seconds"),
        "last_run": dict(last_run) if last_run else None,
        "retry_queue": int(retry_count),
        "conflicts": int(conflict_count),
        "active_mappings": int(active_mappings),
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def cmd_daemon(cfg: dict, db_path: str, log_dir: str):
    log_func = make_log_func(db_path, log_dir)
    engine = build_engine(cfg, db_path, log_func)

    poll_interval = int(cfg.get("sync", {}).get("poll_interval_sec") or cfg.get("server", {}).get("poll_interval_sec", 300))
    poll_interval = max(30, poll_interval)

    log_func("INFO", "daemon", "daemon_started", json.dumps({"poll_interval_sec": poll_interval}, ensure_ascii=False))

    while True:
        try:
            # Refresh index every cycle.
            try:
                from index_generator import write_index_file

                docs_db_path = str(Path(cfg.get("sync", {}).get("local_root") or str(engine.local_root)) / ".local_state" / "docs.db")
                local_root = cfg.get("sync", {}).get("local_root") or str(engine.local_root)
                write_index_file(db_path=docs_db_path, local_root=local_root)
            except Exception as e:
                log_func("WARN", "index", "index_generate_failed", str(e))

            engine.run_once(run_type="scheduled")
        except Exception as e:
            log_func("ERROR", "daemon", "loop_error", str(e))
        time.sleep(poll_interval)


def main():
    cfg = load_cfg()
    db_path = cfg["database"]["path"]
    log_file = cfg["logging"]["file"]
    log_level = cfg.get("logging", {}).get("level", "INFO")
    log_dir = str(Path(log_file).parent)

    init_logger(log_file, log_level)
    init_db(db_path)

    parser = argparse.ArgumentParser(description="Feishu Local Sync Service")
    sub = parser.add_subparsers(dest="cmd")

    run_once_p = sub.add_parser("run-once", help="手动执行一次双向同步")
    run_once_p.add_argument("--run-type", default="manual", help="run_type 标记")

    sub.add_parser("daemon", help="常驻后台轮询同步")
    sub.add_parser("status", help="查看服务状态")

    args = parser.parse_args()

    if args.cmd == "run-once":
        raise SystemExit(cmd_run_once(cfg, db_path, log_dir, run_type=args.run_type))

    if args.cmd == "status":
        raise SystemExit(cmd_status(db_path))

    if args.cmd == "daemon":
        cmd_daemon(cfg, db_path, log_dir)
        return

    parser.print_help()


if __name__ == "__main__":
    main()
