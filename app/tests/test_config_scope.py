from pathlib import Path

from app.core.config import AppConfig, FIXED_LOCAL_ROOT, enforce_local_root_scope, is_local_root_in_scope


def test_is_local_root_in_scope_for_fixed_value():
    assert is_local_root_in_scope(FIXED_LOCAL_ROOT) is True


def test_enforce_local_root_scope_rewrites_out_of_scope_value():
    cfg = AppConfig()
    cfg.sync.local_root = "/tmp/not-allowed"

    locked, requested = enforce_local_root_scope(cfg)

    assert locked is True
    assert requested == "/tmp/not-allowed"
    assert cfg.sync.local_root == FIXED_LOCAL_ROOT


def test_enforce_local_root_scope_keeps_canonical_fixed_root():
    cfg = AppConfig()
    cfg.sync.local_root = str(Path(FIXED_LOCAL_ROOT) / ".." / Path(FIXED_LOCAL_ROOT).name)

    locked, requested = enforce_local_root_scope(cfg)

    assert locked is False
    assert is_local_root_in_scope(requested) is True
    assert cfg.sync.local_root == FIXED_LOCAL_ROOT
