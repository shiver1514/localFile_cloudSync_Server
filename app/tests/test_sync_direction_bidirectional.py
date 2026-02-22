from pathlib import Path

from app.providers.feishu_legacy.sync_engine import SyncEngine, parse_timestamp, remote_fingerprint


def _engine(direction: str) -> SyncEngine:
    cfg = {
        "sync": {
            "local_root": str(Path("/tmp")),
            "default_sync_direction": direction,
        }
    }
    return SyncEngine(cfg=cfg, db_path=str(Path("/tmp") / "sync_direction_test.db"), client=object(), log_func=lambda *_: None)


class _FakeClient:
    def __init__(self):
        self.moved: list[tuple[str, str, str | None]] = []
        self.deleted: list[tuple[str, str]] = []
        self.children: dict[str, list[dict]] = {}
        self.list_errors: dict[str, Exception] = {}

    def list_folder_once(self, folder_token: str | None):
        key = folder_token or ""
        err = self.list_errors.get(key)
        if err is not None:
            raise err
        return list(self.children.get(key, []))

    def move_file(self, file_token: str, file_type: str, folder_token: str | None):
        self.moved.append((file_token, file_type, folder_token))

    def delete_file(self, file_token: str, file_type: str):
        self.deleted.append((file_token, file_type))

    def create_folder(self, name: str, folder_token: str | None):
        token = f"created::{name}"
        self.children.setdefault(folder_token or "", []).append({"type": "folder", "name": name, "token": token})
        self.children.setdefault(token, [])
        return token


def _engine_with_delete_mode(
    *,
    direction: str = "bidirectional",
    remote_delete_mode: str = "recycle_bin",
    cleanup_empty_remote_dirs: bool = False,
    cleanup_remote_missing_dirs_recursive: bool = False,
    client: object | None = None,
) -> SyncEngine:
    cfg = {
        "sync": {
            "local_root": str(Path("/tmp")),
            "default_sync_direction": direction,
            "remote_delete_mode": remote_delete_mode,
            "cleanup_empty_remote_dirs": cleanup_empty_remote_dirs,
            "cleanup_remote_missing_dirs_recursive": cleanup_remote_missing_dirs_recursive,
            "remote_recycle_bin": "SyncRecycleBin",
        }
    }
    return SyncEngine(
        cfg=cfg,
        db_path=str(Path("/tmp") / "sync_direction_test.db"),
        client=client or object(),
        log_func=lambda *_: None,
    )


def test_parse_timestamp_supports_epoch_ms_and_iso():
    assert parse_timestamp("1700000000000") == 1700000000.0
    assert parse_timestamp("2026-02-22T12:00:00+00:00") == 1771761600.0


def test_invalid_direction_falls_back_to_remote_wins():
    engine = _engine("invalid")
    assert engine.default_sync_direction == "remote_wins"


def test_bidirectional_local_missing_deletes_remote_when_remote_unchanged():
    engine = _engine("bidirectional")
    remote_item = {"modified_time": "100", "size": 10}
    row = {"remote_hash": remote_fingerprint(remote_item)}

    assert engine._resolve_local_missing_action(row, remote_item) == "delete_remote"


def test_bidirectional_local_missing_pulls_when_remote_changed():
    engine = _engine("bidirectional")
    remote_item = {"modified_time": "101", "size": 10}
    row = {"remote_hash": "old:hash"}

    assert engine._resolve_local_missing_action(row, remote_item) == "pull_remote"


def test_bidirectional_remote_missing_deletes_local_when_local_unchanged():
    engine = _engine("bidirectional")
    local_item = {"hash": "same"}
    row = {"local_hash": "same"}

    assert engine._resolve_remote_missing_action(row, local_item) == "delete_local"


def test_bidirectional_remote_missing_uploads_when_local_changed():
    engine = _engine("bidirectional")
    local_item = {"hash": "new"}
    row = {"local_hash": "old"}

    assert engine._resolve_remote_missing_action(row, local_item) == "upload_local"


def test_bidirectional_both_changed_prefers_newer_side():
    engine = _engine("bidirectional")
    local_newer = engine._resolve_both_changed_action(
        {"mtime": 200.0},
        {"modified_time": "100", "size": 1},
    )
    remote_newer = engine._resolve_both_changed_action(
        {"mtime": 100.0},
        {"modified_time": "200", "size": 1},
    )

    assert local_newer == "upload_local"
    assert remote_newer == "pull_remote"


def test_invalid_remote_delete_mode_falls_back_to_recycle_bin():
    engine = _engine_with_delete_mode(remote_delete_mode="invalid")
    assert engine.remote_delete_mode == "recycle_bin"


def test_delete_remote_hard_delete_mode_uses_delete_api():
    client = _FakeClient()
    engine = _engine_with_delete_mode(remote_delete_mode="hard_delete", client=client)

    mode = engine._delete_remote("tok-file", "file", "root-token")

    assert mode == "hard_delete"
    assert client.deleted == [("tok-file", "file")]
    assert client.moved == []


def test_delete_remote_recycle_mode_moves_to_recycle_bin():
    client = _FakeClient()
    client.children["root-token"] = [
        {"type": "folder", "name": "SyncRecycleBin", "token": "recycle-token"},
    ]
    engine = _engine_with_delete_mode(remote_delete_mode="recycle_bin", client=client)

    mode = engine._delete_remote("tok-file", "file", "root-token")

    assert mode == "recycle_bin"
    assert client.moved == [("tok-file", "file", "recycle-token")]
    assert client.deleted == []


def test_cleanup_empty_remote_dirs_deletes_only_stale_empty_dirs():
    client = _FakeClient()
    client.children["keep-token"] = []
    client.children["stale-token"] = []
    client.children["recycle-token"] = []
    engine = _engine_with_delete_mode(
        remote_delete_mode="hard_delete",
        cleanup_empty_remote_dirs=True,
        client=client,
    )
    engine._list_remote_tree = lambda _root: ([], {
        "": "root-token",
        "keep": "keep-token",
        "stale": "stale-token",
        "SyncRecycleBin": "recycle-token",
    })

    summary = {
        "errors": 0,
        "remote_soft_deleted": 0,
        "remote_hard_deleted": 0,
        "remote_empty_dirs_deleted": 0,
        "remote_dirs_deleted": 0,
        "remote_dirs_recursive_deleted": 0,
    }
    engine._cleanup_empty_remote_dirs(
        root_token="root-token",
        local_dirs=["keep"],
        local_files={},
        summary=summary,
    )

    assert ("stale-token", "folder") in client.deleted
    assert ("keep-token", "folder") not in client.deleted
    assert summary["remote_empty_dirs_deleted"] == 1
    assert summary["remote_hard_deleted"] == 1
    assert summary["remote_soft_deleted"] == 0
    assert summary["remote_dirs_deleted"] == 1
    assert summary["remote_dirs_recursive_deleted"] == 0


def test_cleanup_missing_remote_dirs_recursive_deletes_non_empty_tree():
    client = _FakeClient()
    client.children["stale-token"] = [
        {"type": "file", "token": "stale-file-token", "name": "old.md"},
        {"type": "folder", "token": "stale-subdir-token", "name": "child"},
    ]
    client.children["stale-subdir-token"] = [
        {"type": "file", "token": "stale-sub-file-token", "name": "child.md"},
    ]
    client.children["recycle-token"] = []
    engine = _engine_with_delete_mode(
        remote_delete_mode="hard_delete",
        cleanup_empty_remote_dirs=True,
        cleanup_remote_missing_dirs_recursive=True,
        client=client,
    )
    engine._list_remote_tree = lambda _root: ([], {
        "": "root-token",
        "stale": "stale-token",
        "SyncRecycleBin": "recycle-token",
    })

    summary = {
        "errors": 0,
        "remote_soft_deleted": 0,
        "remote_hard_deleted": 0,
        "remote_empty_dirs_deleted": 0,
        "remote_dirs_deleted": 0,
        "remote_dirs_recursive_deleted": 0,
    }
    engine._cleanup_empty_remote_dirs(
        root_token="root-token",
        local_dirs=[],
        local_files={},
        summary=summary,
    )

    assert ("stale-file-token", "file") in client.deleted
    assert ("stale-sub-file-token", "file") in client.deleted
    assert ("stale-subdir-token", "folder") in client.deleted
    assert ("stale-token", "folder") in client.deleted
    assert summary["remote_dirs_recursive_deleted"] == 1
    assert summary["remote_dirs_deleted"] >= 1
    assert summary["remote_hard_deleted"] >= 4


def test_cleanup_missing_remote_dirs_recursive_disabled_keeps_non_empty_dir():
    client = _FakeClient()
    client.children["stale-token"] = [
        {"type": "file", "token": "stale-file-token", "name": "old.md"},
    ]
    client.children["recycle-token"] = []
    engine = _engine_with_delete_mode(
        remote_delete_mode="hard_delete",
        cleanup_empty_remote_dirs=True,
        cleanup_remote_missing_dirs_recursive=False,
        client=client,
    )
    engine._list_remote_tree = lambda _root: ([], {
        "": "root-token",
        "stale": "stale-token",
        "SyncRecycleBin": "recycle-token",
    })

    summary = {
        "errors": 0,
        "remote_soft_deleted": 0,
        "remote_hard_deleted": 0,
        "remote_empty_dirs_deleted": 0,
        "remote_dirs_deleted": 0,
        "remote_dirs_recursive_deleted": 0,
    }
    engine._cleanup_empty_remote_dirs(
        root_token="root-token",
        local_dirs=[],
        local_files={},
        summary=summary,
    )

    assert ("stale-token", "folder") not in client.deleted
    assert summary["remote_dirs_deleted"] == 0
    assert summary["remote_hard_deleted"] == 0


def test_dedup_not_found_error_is_ignored():
    client = _FakeClient()
    client.list_errors["root-token"] = RuntimeError(
        "list_files_failed: {'code': 1061007, 'msg': 'file has been delete.'}"
    )
    engine = _engine_with_delete_mode(client=client)

    # Should not raise, and should be treated as benign concurrent deletion.
    engine._dedup_remote_same_name("root-token")
