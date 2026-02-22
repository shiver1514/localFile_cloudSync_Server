from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import AppConfig
from app.web import api as api_module


def _build_client() -> TestClient:
    app = FastAPI()
    app.include_router(api_module.router)
    return TestClient(app)


def _reset_event_state() -> None:
    api_module._event_recent_ids.clear()
    api_module._event_state.clear()
    api_module._event_state.update(
        {
            "enabled": False,
            "verify_token_configured": False,
            "encrypt_key_configured": False,
            "debounce_sec": 15,
            "trigger_types": list(api_module.EVENT_DEFAULT_TRIGGER_TYPES),
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
    )


def _mock_cfg() -> AppConfig:
    cfg = AppConfig()
    cfg.sync.event_callback_enabled = True
    cfg.sync.event_verify_token = "verify-token-123"
    cfg.sync.event_encrypt_key = ""
    cfg.sync.event_debounce_sec = 0
    cfg.sync.event_trigger_types = ["drive.file.edit_v1", "drive.file.title_updated_v1"]
    return cfg


def _event_payload(event_id: str = "evt-1", event_type: str = "drive.file.edit_v1") -> dict:
    return {
        "schema": "2.0",
        "header": {
            "event_id": event_id,
            "token": "verify-token-123",
            "create_time": "1771761600000",
            "event_type": event_type,
            "tenant_key": "tenant_key",
            "app_id": "cli_xxx",
        },
        "event": {"file_token": "boxcn123"},
        "type": "event_callback",
    }


def test_event_url_verification_success(monkeypatch):
    _reset_event_state()
    monkeypatch.setattr(api_module, "load_config", lambda: _mock_cfg())

    client = _build_client()
    resp = client.post(
        "/api/events/feishu",
        json={"type": "url_verification", "token": "verify-token-123", "challenge": "hello-world"},
    )

    assert resp.status_code == 200
    assert resp.json() == {"challenge": "hello-world"}


def test_event_callback_queues_sync_when_event_type_matched(monkeypatch):
    _reset_event_state()
    monkeypatch.setattr(api_module, "load_config", lambda: _mock_cfg())
    calls: list[tuple[str, str, int]] = []

    def _fake_run(event_type: str, event_id: str, debounce_sec: int):
        calls.append((event_type, event_id, debounce_sec))
        api_module._event_state_update(pending=False, trigger_count=api_module._as_int(api_module._event_state.get("trigger_count"), 0) + 1)

    monkeypatch.setattr(api_module, "_run_event_sync_job", _fake_run)

    client = _build_client()
    resp = client.post("/api/events/feishu", json=_event_payload("evt-queue-1", "drive.file.edit_v1"))

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["queued"] is True
    assert calls == [("drive.file.edit_v1", "evt-queue-1", 0)]


def test_event_callback_unmatched_event_type_is_ignored(monkeypatch):
    _reset_event_state()
    monkeypatch.setattr(api_module, "load_config", lambda: _mock_cfg())
    monkeypatch.setattr(api_module, "_run_event_sync_job", lambda *_args: None)

    client = _build_client()
    resp = client.post("/api/events/feishu", json=_event_payload("evt-um-1", "im.message.receive_v1"))

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["queued"] is False
    assert payload["reason"] == "unmatched_event_type"


def test_event_callback_rejects_invalid_verify_token(monkeypatch):
    _reset_event_state()
    monkeypatch.setattr(api_module, "load_config", lambda: _mock_cfg())

    bad = _event_payload("evt-bad-token", "drive.file.edit_v1")
    bad["header"]["token"] = "token-mismatch"
    client = _build_client()
    resp = client.post("/api/events/feishu", json=bad)

    assert resp.status_code == 401


def test_event_callback_dedups_same_event_id(monkeypatch):
    _reset_event_state()
    monkeypatch.setattr(api_module, "load_config", lambda: _mock_cfg())
    monkeypatch.setattr(api_module, "_run_event_sync_job", lambda *_args: None)

    client = _build_client()
    first = client.post("/api/events/feishu", json=_event_payload("evt-dup-1", "drive.file.edit_v1"))
    second = client.post("/api/events/feishu", json=_event_payload("evt-dup-1", "drive.file.edit_v1"))

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["queued"] is False
    assert second.json()["reason"] == "duplicate_event"


def test_event_callback_returns_503_when_verify_token_missing(monkeypatch):
    _reset_event_state()
    cfg = _mock_cfg()
    cfg.sync.event_verify_token = ""
    monkeypatch.setattr(api_module, "load_config", lambda: cfg)

    client = _build_client()
    resp = client.post("/api/events/feishu", json=_event_payload("evt-no-token", "drive.file.edit_v1"))

    assert resp.status_code == 503
    assert resp.json()["detail"] == "event_verify_token_missing"
