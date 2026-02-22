import json
from pathlib import Path

from app.core.config import AppConfig
from app.web import api as api_module


def test_healthz_returns_alive():
    payload = api_module.healthz()
    assert payload["ok"] is True
    assert payload["status"] == "alive"
    assert "checked_at" in payload


def test_readyz_returns_200_when_checks_pass(monkeypatch, tmp_path: Path):
    cfg = AppConfig()
    cfg.database.path = str(tmp_path / "runtime" / "service.db")
    cfg.logging.file = str(tmp_path / "runtime" / "service.log")
    cfg.sync.local_root = cfg.sync.local_root

    monkeypatch.setattr(api_module, "load_config", lambda: cfg)
    monkeypatch.setattr(api_module, "is_local_root_in_scope", lambda _value: True)
    monkeypatch.setattr(
        api_module,
        "_scheduler_state_snapshot",
        lambda: {
            "initialized": True,
            "running": True,
            "enabled": True,
            "configured_interval_sec": 300,
            "effective_interval_sec": 300,
            "last_started_at": None,
            "last_finished_at": None,
            "next_run_at": None,
            "next_run_in_sec": None,
            "last_result": "success",
            "last_error": None,
            "run_count": 1,
            "skipped_busy_count": 0,
        },
    )

    resp = api_module.readyz()
    assert resp.status_code == 200
    payload = json.loads(resp.body.decode("utf-8"))
    assert payload["ok"] is True
    assert payload["checks"]["config_load"] is True
    assert payload["checks"]["database_parent_ready"] is True
    assert payload["checks"]["log_parent_ready"] is True
    assert payload["checks"]["scheduler_running"] is True
    assert payload["errors"] == []


def test_readyz_returns_503_when_config_load_fails(monkeypatch):
    def _raise_load_config():
        raise RuntimeError("boom")

    monkeypatch.setattr(api_module, "load_config", _raise_load_config)
    monkeypatch.setattr(api_module, "_scheduler_state_snapshot", lambda: {"running": False, "enabled": False})

    resp = api_module.readyz()
    assert resp.status_code == 503
    payload = json.loads(resp.body.decode("utf-8"))
    assert payload["ok"] is False
    assert payload["checks"]["config_load"] is False
    assert any("config_load_failed" in err for err in payload["errors"])


def test_readyz_warns_when_event_callback_enabled_without_verify_token(monkeypatch, tmp_path: Path):
    cfg = AppConfig()
    cfg.database.path = str(tmp_path / "runtime" / "service.db")
    cfg.logging.file = str(tmp_path / "runtime" / "service.log")
    cfg.sync.event_callback_enabled = True
    cfg.sync.event_verify_token = ""

    monkeypatch.setattr(api_module, "load_config", lambda: cfg)
    monkeypatch.setattr(api_module, "is_local_root_in_scope", lambda _value: True)
    monkeypatch.setattr(
        api_module,
        "_scheduler_state_snapshot",
        lambda: {
            "initialized": True,
            "running": True,
            "enabled": True,
            "configured_interval_sec": 300,
            "effective_interval_sec": 300,
            "last_started_at": None,
            "last_finished_at": None,
            "next_run_at": None,
            "next_run_in_sec": None,
            "last_result": "success",
            "last_error": None,
            "run_count": 1,
            "skipped_busy_count": 0,
        },
    )

    resp = api_module.readyz()
    assert resp.status_code == 200
    payload = json.loads(resp.body.decode("utf-8"))
    assert payload["checks"]["event_callback_config_ok"] is False
    assert "event_callback_enabled_but_verify_token_missing" in payload["warnings"]
