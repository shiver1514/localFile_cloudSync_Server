from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import AppConfig
from app.web import api as api_module


def _build_client() -> TestClient:
    app = FastAPI()
    app.include_router(api_module.router)
    return TestClient(app)


def test_healthz_returns_alive():
    client = _build_client()
    resp = client.get("/api/healthz")
    assert resp.status_code == 200
    payload = resp.json()
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

    client = _build_client()
    resp = client.get("/api/readyz")
    assert resp.status_code == 200
    payload = resp.json()
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

    client = _build_client()
    resp = client.get("/api/readyz")
    assert resp.status_code == 503
    payload = resp.json()
    assert payload["ok"] is False
    assert payload["checks"]["config_load"] is False
    assert any("config_load_failed" in err for err in payload["errors"])
