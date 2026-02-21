import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .db import get_conn


def sha256_file(path: Path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 64), b""):
            h.update(chunk)
    return h.hexdigest()


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def remote_fingerprint(item: dict):
    return f"{item.get('modified_time', '')}:{item.get('size', 0)}"


def safe_rel_path(value: str):
    return str(Path(value).as_posix()).lstrip("/")


def scan_local_files(local_root: str, exclude_dirs: Optional[List[str]] = None):
    base = Path(local_root)
    if not base.exists():
        return {}

    excludes = set(exclude_dirs or [])
    files = {}

    for root, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in excludes]
        root_path = Path(root)
        for name in filenames:
            full = root_path / name
            if not full.is_file():
                continue
            rel = safe_rel_path(str(full.relative_to(base)))
            st = full.stat()
            files[rel] = {
                "rel_path": rel,
                "full_path": str(full),
                "hash": sha256_file(full),
                "mtime": st.st_mtime,
                "size": st.st_size,
            }
    return files


def scan_local_dirs(local_root: str, exclude_dirs: Optional[List[str]] = None) -> List[str]:
    """Return a list of relative directory paths ("a/b") including empty ones.

    This enables structure-driven sync (folders + files).
    """

    base = Path(local_root)
    if not base.exists():
        return []

    excludes = set(exclude_dirs or [])
    dirs: List[str] = []

    for root, dirnames, _filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in excludes]
        root_path = Path(root)
        if root_path == base:
            continue
        rel = safe_rel_path(str(root_path.relative_to(base)))
        if rel:
            dirs.append(rel)

    dirs.sort()
    return dirs


class SyncEngine:
    def __init__(self, cfg: dict, db_path: str, client, log_func):
        self.cfg = cfg
        self.db_path = db_path
        self.client = client
        self.log_func = log_func

        sync_cfg = cfg.get("sync", {})
        mappings = sync_cfg.get("mappings", [])
        primary_mapping = None
        for m in mappings:
            if m.get("enabled"):
                primary_mapping = m
                break
        if not primary_mapping and mappings:
            primary_mapping = mappings[0]

        self.local_root = Path(
            sync_cfg.get("local_root")
            or (primary_mapping or {}).get("local_path")
            or "/home/n150/openclaw_workspace/search_docs"
        )
        self.remote_root_token = (
            sync_cfg.get("remote_folder_token")
            if sync_cfg.get("remote_folder_token") is not None
            else (primary_mapping or {}).get("remote_folder_token", "")
        )

        self.conflict_policy = sync_cfg.get("conflict_policy", "keep_both")
        # initial_sync_strategy:
        # - local_wins: first-time sync uses local as source of truth
        # - remote_wins: first-time sync uses remote as source of truth
        # - dry_run: never soft-delete during initial sync
        self.initial_sync_strategy = sync_cfg.get("initial_sync_strategy", "local_wins")
        self.default_sync_direction = sync_cfg.get("default_sync_direction", "remote_wins")
        self.recycle_bin_name = sync_cfg.get("remote_recycle_bin", "SyncRecycleBin")
        self.local_trash_dir_name = sync_cfg.get("local_trash_dir", ".sync_trash")
        self.exclude_dirs = sync_cfg.get(
            "exclude_dirs",
            [".git", ".sync_trash", ".sync_quarantine", "__pycache__"],
        )
        self.max_retry = int(sync_cfg.get("max_retry", 5))

        self._remote_folder_cache: Dict[str, str] = {}
        self._children_folder_cache: Dict[str, Dict[str, str]] = {}

    def _log(self, level: str, module: str, message: str, detail: Optional[str] = None):
        self.log_func(level, module, message, detail)

    def _db(self):
        return get_conn(self.db_path)

    def _insert_sync_run(self, run_type: str):
        conn = self._db()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO sync_runs(run_type,status,started_at,summary_json) VALUES (?,?,?,?)",
            (run_type, "running", now_iso(), "{}"),
        )
        rid = cur.lastrowid
        conn.commit()
        conn.close()
        return rid

    def _finish_sync_run(self, run_id: int, status: str, summary: dict):
        conn = self._db()
        conn.execute(
            "UPDATE sync_runs SET status=?, finished_at=?, summary_json=? WHERE id=?",
            (status, now_iso(), json.dumps(summary, ensure_ascii=False), run_id),
        )
        conn.commit()
        conn.close()

    def _load_mappings(self):
        conn = self._db()
        rows = conn.execute(
            "SELECT * FROM file_mappings WHERE status!='deleted' ORDER BY id"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def _update_mapping(self, rel_path: str, remote_token: str, remote_type: str, local_hash: str, remote_hash: str,
                        local_mtime: float, remote_modified_time: str, status: str = "active", conflict: int = 0,
                        extra: Optional[dict] = None):
        rel_path = safe_rel_path(rel_path)
        extra_json = json.dumps(extra or {}, ensure_ascii=False)

        conn = self._db()
        row = conn.execute("SELECT id FROM file_mappings WHERE local_rel_path=?", (rel_path,)).fetchone()
        if not row:
            row = conn.execute("SELECT id FROM file_mappings WHERE remote_token=?", (remote_token,)).fetchone()

        if row:
            conn.execute(
                """
                UPDATE file_mappings
                   SET local_rel_path=?, remote_token=?, remote_type=?,
                       local_hash=?, remote_hash=?, local_mtime=?, remote_modified_time=?,
                       status=?, conflict=?, last_synced_at=?, extra_json=?, updated_at=CURRENT_TIMESTAMP
                 WHERE id=?
                """,
                (
                    rel_path,
                    remote_token,
                    remote_type,
                    local_hash,
                    remote_hash,
                    local_mtime,
                    remote_modified_time,
                    status,
                    conflict,
                    now_iso(),
                    extra_json,
                    row["id"],
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO file_mappings(
                    local_rel_path,remote_token,remote_type,
                    local_hash,remote_hash,local_mtime,remote_modified_time,
                    status,conflict,last_synced_at,extra_json
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    rel_path,
                    remote_token,
                    remote_type,
                    local_hash,
                    remote_hash,
                    local_mtime,
                    remote_modified_time,
                    status,
                    conflict,
                    now_iso(),
                    extra_json,
                ),
            )
        conn.commit()
        conn.close()

    def _mark_deleted_mapping(self, local_rel_path: str):
        conn = self._db()
        conn.execute(
            "UPDATE file_mappings SET status='deleted', updated_at=CURRENT_TIMESTAMP WHERE local_rel_path=?",
            (safe_rel_path(local_rel_path),),
        )
        conn.commit()
        conn.close()

    def _rename_mapping_path(self, old_rel: str, new_rel: str):
        conn = self._db()
        conn.execute(
            "UPDATE file_mappings SET local_rel_path=?, updated_at=CURRENT_TIMESTAMP WHERE local_rel_path=?",
            (safe_rel_path(new_rel), safe_rel_path(old_rel)),
        )
        conn.commit()
        conn.close()

    def _insert_tombstone(self, side: str, local_rel_path: str, remote_token: str, reason: str):
        conn = self._db()
        conn.execute(
            "INSERT INTO tombstones(side,local_rel_path,remote_token,reason) VALUES (?,?,?,?)",
            (side, safe_rel_path(local_rel_path) if local_rel_path else None, remote_token, reason),
        )
        conn.commit()
        conn.close()

    def _enqueue_retry(self, op_type: str, payload: dict, last_error: str, attempt_count: int = 0):
        wait_sec = min(300, 2 ** min(attempt_count + 1, 8))
        next_retry_at = (datetime.now() + timedelta(seconds=wait_sec)).isoformat(timespec="seconds")
        conn = self._db()
        conn.execute(
            """
            INSERT INTO retry_queue(op_type,payload_json,attempt_count,next_retry_at,last_error)
            VALUES (?,?,?,?,?)
            """,
            (op_type, json.dumps(payload, ensure_ascii=False), attempt_count, next_retry_at, last_error),
        )
        conn.commit()
        conn.close()

    def _due_retries(self):
        conn = self._db()
        rows = conn.execute(
            """
            SELECT * FROM retry_queue
             WHERE next_retry_at <= ?
             ORDER BY id
             LIMIT 50
            """,
            (now_iso(),),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def _retry_success(self, row_id: int):
        conn = self._db()
        conn.execute("DELETE FROM retry_queue WHERE id=?", (row_id,))
        conn.commit()
        conn.close()

    def _retry_fail(self, row: dict, error: str):
        attempt = int(row.get("attempt_count", 0)) + 1
        if attempt >= self.max_retry:
            conn = self._db()
            conn.execute("DELETE FROM retry_queue WHERE id=?", (row["id"],))
            conn.commit()
            conn.close()
            self._log("ERROR", "retry", "retry_discarded", json.dumps({"id": row["id"], "error": error}, ensure_ascii=False))
            return

        wait_sec = min(600, 2 ** min(attempt + 1, 9))
        next_retry_at = (datetime.now() + timedelta(seconds=wait_sec)).isoformat(timespec="seconds")
        conn = self._db()
        conn.execute(
            """
            UPDATE retry_queue
               SET attempt_count=?, next_retry_at=?, last_error=?, updated_at=CURRENT_TIMESTAMP
             WHERE id=?
            """,
            (attempt, next_retry_at, error, row["id"]),
        )
        conn.commit()
        conn.close()

    def _execute_retry_payload(self, payload: dict, root_token: str):
        kind = payload.get("kind")
        if kind == "upload":
            rel = payload["rel_path"]
            if rel.startswith(f"{self.local_trash_dir_name}/") or rel.startswith(".sync_quarantine/"):
                raise RuntimeError(f"retry_skip_local_internal:{rel}")
            full = self.local_root / rel
            if not full.exists():
                raise RuntimeError(f"retry_upload_local_missing:{rel}")
            self._upload_local_file(rel, root_token)
        elif kind == "pull":
            rel = payload["rel_path"]
            if rel.startswith(f"{self.local_trash_dir_name}/") or rel.startswith(".sync_quarantine/"):
                raise RuntimeError(f"retry_skip_local_internal:{rel}")
            remote_item = payload["remote_item"]
            self._pull_remote_to_local(rel, remote_item)
        elif kind == "soft_delete_remote":
            self._soft_delete_remote(payload["remote_token"], payload.get("remote_type", "file"), root_token)
        elif kind == "soft_delete_local":
            self._soft_delete_local(payload["rel_path"])
        else:
            raise RuntimeError(f"retry_unknown_kind:{kind}")

    def _list_remote_tree(self, root_token: str):
        files = []
        folders = {"": root_token}

        def walk(folder_token: str, prefix: str):
            children = self.client.list_folder_once(folder_token)
            folder_children = {}
            for item in children:
                token = item.get("token")
                if not token:
                    continue
                item_type = item.get("type") or "file"
                name = item.get("name") or item.get("title") or token
                path = f"{prefix}/{name}" if prefix else name

                if item_type == "folder":
                    folder_children[name] = token
                    folders[path] = token
                    if path == self.recycle_bin_name or path.startswith(f"{self.recycle_bin_name}/"):
                        continue
                    walk(token, path)
                else:
                    if path == self.recycle_bin_name or path.startswith(f"{self.recycle_bin_name}/"):
                        continue
                    files.append(
                        {
                            "token": token,
                            "name": name,
                            "type": item_type,
                            "size": int(item.get("size") or 0),
                            "modified_time": item.get("modified_time") or item.get("modified_at") or "",
                            "folder_token": folder_token,
                            "path": path,
                        }
                    )

            self._children_folder_cache[folder_token] = folder_children

        walk(root_token, "")
        self._remote_folder_cache = folders
        return files, folders

    def _find_child_folder(self, parent_token: str, name: str) -> Optional[str]:
        cached = self._children_folder_cache.get(parent_token)
        if cached is not None and name in cached:
            return cached[name]

        children = self.client.list_folder_once(parent_token)
        folder_map = {}
        for item in children:
            if item.get("type") == "folder" and item.get("token"):
                folder_map[item.get("name") or item.get("title") or item["token"]] = item["token"]
        self._children_folder_cache[parent_token] = folder_map
        return folder_map.get(name)

    def _ensure_remote_folder(self, root_token: str, rel_dir: str):
        rel_dir = safe_rel_path(rel_dir)
        if not rel_dir or rel_dir == ".":
            return root_token

        if rel_dir in self._remote_folder_cache:
            return self._remote_folder_cache[rel_dir]

        current = root_token
        current_rel = ""
        for part in Path(rel_dir).parts:
            current_rel = f"{current_rel}/{part}" if current_rel else part
            if current_rel in self._remote_folder_cache:
                current = self._remote_folder_cache[current_rel]
                continue

            found = self._find_child_folder(current, part)
            if not found:
                found = self.client.create_folder(part, current)
                self._children_folder_cache.setdefault(current, {})[part] = found

            self._remote_folder_cache[current_rel] = found
            current = found

        return current

    def _ensure_remote_recycle_bin(self, root_token: str):
        token = self._remote_folder_cache.get(self.recycle_bin_name)
        if token:
            return token

        found = self._find_child_folder(root_token, self.recycle_bin_name)
        if not found:
            found = self.client.create_folder(self.recycle_bin_name, root_token)
        self._remote_folder_cache[self.recycle_bin_name] = found
        return found

    def _dedup_remote_same_name(self, root_token: str):
        """Hard-delete duplicate same-name items under the same folder.

        Feishu Drive can contain multiple items with the same name in one folder.
        This breaks path-based sync and surprises humans.

        Policy: keep the newest by `modified_time` (fallback: keep first), delete the rest.
        """

        def item_name(it: dict) -> str:
            return it.get("name") or it.get("title") or it.get("token") or ""

        def item_mtime(it: dict) -> int:
            try:
                return int(it.get("modified_time") or it.get("modified_at") or 0)
            except Exception:
                return 0

        # Walk using API to get per-folder children.
        stack = [("", root_token)]
        while stack:
            _path, folder_token = stack.pop()
            children = self.client.list_folder_once(folder_token)
            groups: Dict[str, List[dict]] = {}
            for it in children:
                n = item_name(it)
                if not n:
                    continue
                groups.setdefault(n, []).append(it)

            for n, items in groups.items():
                if len(items) <= 1:
                    continue
                items_sorted = sorted(items, key=item_mtime, reverse=True)
                keep = items_sorted[0]
                for victim in items_sorted[1:]:
                    tok = victim.get("token")
                    typ = victim.get("type") or "file"
                    if tok:
                        self.client.delete_file(tok, typ)
                        self._log(
                            "WARN",
                            "sync",
                            "remote_dedup_deleted",
                            json.dumps({"name": n, "token": tok, "type": typ}, ensure_ascii=False),
                        )

                # If keep is a folder, still traverse it.
                if keep.get("type") == "folder" and keep.get("token"):
                    stack.append((_path + "/" + n if _path else n, keep["token"]))

            # Traverse all folders (after potential deletions)
            for it in children:
                if (it.get("type") == "folder") and it.get("token"):
                    stack.append((_path + "/" + item_name(it) if _path else item_name(it), it["token"]))

    def _soft_delete_local(self, rel_path: str):
        rel_path = safe_rel_path(rel_path)
        src = self.local_root / rel_path
        if not src.exists():
            return

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = self.local_root / self.local_trash_dir_name / ts / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dest))

    def _soft_delete_remote(self, remote_token: str, remote_type: str, root_token: str):
        recycle = self._ensure_remote_recycle_bin(root_token)
        self.client.move_file(remote_token, remote_type or "file", recycle)

    def _upload_local_file(self, rel_path: str, root_token: str, old_remote_token: Optional[str] = None,
                           old_remote_type: str = "file"):
        rel_path = safe_rel_path(rel_path)
        local_file = self.local_root / rel_path
        parent_rel = safe_rel_path(str(Path(rel_path).parent))
        if parent_rel == ".":
            parent_rel = ""
        remote_folder_token = self._ensure_remote_folder(root_token, parent_rel)
        uploaded = self.client.upload_file(str(local_file), remote_folder_token, file_name=Path(rel_path).name)
        new_token = uploaded.get("file_token")
        if not new_token:
            raise RuntimeError("upload_no_file_token")

        remote_item = {
            "token": new_token,
            "type": "file",
            "size": int(local_file.stat().st_size),
            "modified_time": now_iso(),
            "path": rel_path,
        }

        try:
            folder_items = self.client.list_folder_once(remote_folder_token)
            hit = next((item for item in folder_items if item.get("token") == new_token), None)
            if hit:
                remote_item["type"] = hit.get("type") or remote_item["type"]
                remote_item["size"] = int(hit.get("size") or remote_item["size"])
                remote_item["modified_time"] = hit.get("modified_time") or remote_item["modified_time"]
        except Exception:
            pass

        if old_remote_token and old_remote_token != new_token:
            self._soft_delete_remote(old_remote_token, old_remote_type, root_token)

        local_hash = sha256_file(local_file)
        local_mtime = local_file.stat().st_mtime
        self._update_mapping(
            rel_path=rel_path,
            remote_token=new_token,
            remote_type=remote_item["type"],
            local_hash=local_hash,
            remote_hash=remote_fingerprint(remote_item),
            local_mtime=local_mtime,
            remote_modified_time=remote_item.get("modified_time", ""),
            status="active",
            conflict=0,
        )

    def _pull_remote_to_local(self, rel_path: str, remote_item: dict):
        rel_path = safe_rel_path(rel_path)
        local_path = self.local_root / rel_path
        local_path.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            self.client.download_file(remote_item["token"], str(tmp_path))
            shutil.move(str(tmp_path), str(local_path))
        finally:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)

        local_hash = sha256_file(local_path)
        local_mtime = local_path.stat().st_mtime
        self._update_mapping(
            rel_path=rel_path,
            remote_token=remote_item["token"],
            remote_type=remote_item.get("type") or "file",
            local_hash=local_hash,
            remote_hash=remote_fingerprint(remote_item),
            local_mtime=local_mtime,
            remote_modified_time=remote_item.get("modified_time", ""),
            status="active",
            conflict=0,
        )

    def _create_conflict_copy(self, rel_path: str, remote_item: dict):
        rel_path = safe_rel_path(rel_path)
        base = self.local_root / rel_path
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        conflict_path = base.parent / f"{base.name}.remote_conflict_{ts}"
        self.client.download_file(remote_item["token"], str(conflict_path))

        local_hash = ""
        local_mtime = 0.0
        if base.exists() and base.is_file():
            local_hash = sha256_file(base)
            local_mtime = base.stat().st_mtime

        conn = self._db()
        conn.execute(
            """
            UPDATE file_mappings
               SET conflict=1,
                   status='conflict',
                   local_hash=?,
                   local_mtime=?,
                   remote_hash=?,
                   remote_modified_time=?,
                   updated_at=CURRENT_TIMESTAMP
             WHERE local_rel_path=?
            """,
            (
                local_hash,
                local_mtime,
                remote_fingerprint(remote_item),
                remote_item.get("modified_time", ""),
                rel_path,
            ),
        )
        conn.commit()
        conn.close()

    def _process_due_retries(self, root_token: str, summary: dict):
        rows = self._due_retries()
        if not rows:
            return
        for row in rows:
            try:
                payload = json.loads(row.get("payload_json") or "{}")
                self._execute_retry_payload(payload, root_token)
                self._retry_success(row["id"])
                summary["retry_success"] += 1
            except Exception as e:
                err = str(e)
                # Hard discard for 404: remote resource gone; keep tombstone and drop the retry.
                if "download_failed_status_404" in err:
                    payload = {}
                    try:
                        payload = json.loads(row.get("payload_json") or "{}")
                    except Exception:
                        payload = {}
                    remote_item = payload.get("remote_item") or {}
                    rel = payload.get("rel_path") or ""
                    self._insert_tombstone("remote", rel, remote_item.get("token") or "", "retry_remote_404")
                    self._retry_success(row["id"])
                    summary["retry_failed"] += 1
                    continue

                self._retry_fail(row, err)
                summary["retry_failed"] += 1
                self._log("ERROR", "retry", "retry_failed", json.dumps({"id": row["id"], "error": str(e)}, ensure_ascii=False))

    def run_once(self, run_type: str = "manual"):
        run_id = self._insert_sync_run(run_type)
        summary = {
            "run_id": run_id,
            "local_root": str(self.local_root),
            "remote_root_token": "",
            "local_total": 0,
            "remote_total": 0,
            "uploaded": 0,
            "downloaded": 0,
            "renamed": 0,
            "conflicts": 0,
            "remote_soft_deleted": 0,
            "local_soft_deleted": 0,
            "retry_success": 0,
            "retry_failed": 0,
            "errors": 0,
        }

        try:
            root_token = self.remote_root_token or self.client.get_root_folder_token()
            summary["remote_root_token"] = root_token

            self.local_root.mkdir(parents=True, exist_ok=True)
            local_dirs = scan_local_dirs(str(self.local_root), self.exclude_dirs)
            local_files = scan_local_files(str(self.local_root), self.exclude_dirs)
            summary["local_total"] = len(local_files)

            remote_files, remote_folders = self._list_remote_tree(root_token)
            summary["remote_total"] = len(remote_files)

            # Anti-footgun: deduplicate same-name items under the same remote folder.
            # Keep the newest (modified_time), hard-delete the rest.
            try:
                self._dedup_remote_same_name(root_token)
                # refresh caches after deletion
                remote_files, remote_folders = self._list_remote_tree(root_token)
                summary["remote_total"] = len(remote_files)
            except Exception as e:
                summary["errors"] += 1
                self._log(
                    "WARN",
                    "sync",
                    "remote_dedup_failed",
                    json.dumps({"error": str(e)}, ensure_ascii=False),
                )

            self._process_due_retries(root_token, summary)

            # Ensure remote folder structure exists for all local directories.
            for rel_dir in local_dirs:
                try:
                    self._ensure_remote_folder(root_token, rel_dir)
                except Exception as e:
                    summary["errors"] += 1
                    self._log("ERROR", "sync", "ensure_remote_folder_failed", json.dumps({"dir": rel_dir, "error": str(e)}, ensure_ascii=False))

            # Initial sync guard: if we have no mappings yet, pick a source-of-truth.
            # Default per config: local_wins.
            conn = self._db()
            mapping_count = conn.execute("SELECT COUNT(1) FROM file_mappings").fetchone()[0]
            conn.close()
            if mapping_count == 0:
                if self.initial_sync_strategy == "local_wins":
                    remote_files = []
                    summary["remote_total"] = 0
                elif self.initial_sync_strategy == "remote_wins":
                    local_files = {}
                    summary["local_total"] = 0
                elif self.initial_sync_strategy == "dry_run":
                    pass

            mappings = self._load_mappings()
            map_by_path = {m["local_rel_path"]: m for m in mappings}
            map_by_token = {m["remote_token"]: m for m in mappings if m.get("remote_token")}

            remote_by_token = {r["token"]: r for r in remote_files}
            remote_by_path = {r["path"]: r for r in remote_files}

            unmapped_local_by_hash: Dict[str, List[str]] = {}
            for rel, info in local_files.items():
                if rel not in map_by_path:
                    unmapped_local_by_hash.setdefault(info["hash"], []).append(rel)

            for rel, row in list(map_by_path.items()):
                remote_item = remote_by_token.get(row["remote_token"])
                local_item = local_files.get(rel)

                if not local_item and remote_item and row.get("local_hash"):
                    candidates = unmapped_local_by_hash.get(row.get("local_hash"), [])
                    if candidates:
                        new_rel = candidates.pop(0)
                        self._rename_mapping_path(rel, new_rel)
                        if Path(new_rel).name != remote_item.get("name"):
                            try:
                                self.client.rename_file(remote_item["token"], Path(new_rel).name)
                            except Exception as e:
                                summary["errors"] += 1
                                self._log("WARN", "sync", "remote_rename_failed", str(e))
                        summary["renamed"] += 1
                        self._log("INFO", "sync", "local_rename_detected", json.dumps({"old": rel, "new": new_rel}, ensure_ascii=False))

            mappings = self._load_mappings()
            map_by_path = {m["local_rel_path"]: m for m in mappings}
            map_by_token = {m["remote_token"]: m for m in mappings if m.get("remote_token")}

            for rel, row in list(map_by_path.items()):
                local_item = local_files.get(rel)
                remote_item = remote_by_token.get(row["remote_token"])

                if not local_item and remote_item:
                    # Default: remote wins → pull remote to local.
                    if self.default_sync_direction == "remote_wins":
                        try:
                            self._pull_remote_to_local(rel, remote_item)
                            summary["downloaded"] += 1
                            continue
                        except Exception as e:
                            err = str(e)
                            if "download_failed_status_404" in err:
                                self._insert_tombstone("remote", rel, remote_item.get("token"), "remote_404")
                                continue
                            self._enqueue_retry(
                                "pull",
                                {"kind": "pull", "rel_path": rel, "remote_item": remote_item},
                                err,
                            )
                            summary["errors"] += 1
                            continue

                    # local_wins: treat as local deleted → delete remote.
                    try:
                        self._soft_delete_remote(remote_item["token"], remote_item.get("type", "file"), root_token)
                        self._insert_tombstone("local", rel, remote_item["token"], "local_deleted")
                        self._mark_deleted_mapping(rel)
                        summary["remote_soft_deleted"] += 1
                    except Exception as e:
                        self._enqueue_retry(
                            "soft_delete_remote",
                            {
                                "kind": "soft_delete_remote",
                                "remote_token": remote_item["token"],
                                "remote_type": remote_item.get("type", "file"),
                            },
                            str(e),
                        )
                        summary["errors"] += 1
                    continue

                if local_item and not remote_item:
                    # Default: remote wins → remote missing means local should be removed.
                    if self.default_sync_direction == "remote_wins":
                        try:
                            self._soft_delete_local(rel)
                            self._insert_tombstone("remote", rel, row.get("remote_token"), "remote_deleted")
                            self._mark_deleted_mapping(rel)
                            summary["local_soft_deleted"] += 1
                        except Exception as e:
                            self._enqueue_retry(
                                "soft_delete_local",
                                {"kind": "soft_delete_local", "rel_path": rel},
                                str(e),
                            )
                            summary["errors"] += 1
                        continue

                    # local_wins: re-upload.
                    try:
                        self._upload_local_file(rel, root_token)
                        summary["uploaded"] += 1
                    except Exception as e:
                        self._enqueue_retry("upload", {"kind": "upload", "rel_path": rel}, str(e))
                        summary["errors"] += 1
                    continue

                if not local_item and not remote_item:
                    self._mark_deleted_mapping(rel)
                    continue

                local_changed = local_item["hash"] != (row.get("local_hash") or "")
                remote_changed = remote_fingerprint(remote_item) != (row.get("remote_hash") or "")

                # Default policy: remote wins when both changed.
                if local_changed and remote_changed:
                    try:
                        self._pull_remote_to_local(rel, remote_item)
                        summary["downloaded"] += 1
                    except Exception as e:
                        err = str(e)
                        if "download_failed_status_404" in err:
                            self._insert_tombstone("remote", rel, remote_item.get("token"), "remote_404")
                        else:
                            self._enqueue_retry(
                                "pull",
                                {"kind": "pull", "rel_path": rel, "remote_item": remote_item},
                                err,
                            )
                            summary["errors"] += 1
                    continue

                if local_changed and not remote_changed:
                    try:
                        self._upload_local_file(
                            rel,
                            root_token,
                            old_remote_token=row.get("remote_token"),
                            old_remote_type=row.get("remote_type") or "file",
                        )
                        summary["uploaded"] += 1
                    except Exception as e:
                        self._enqueue_retry(
                            "upload",
                            {"kind": "upload", "rel_path": rel},
                            str(e),
                        )
                        summary["errors"] += 1
                    continue

                if remote_changed and not local_changed:
                    try:
                        self._pull_remote_to_local(rel, remote_item)
                        summary["downloaded"] += 1
                    except Exception as e:
                        err = str(e)
                        if "download_failed_status_404" in err:
                            # Remote resource already gone / not downloadable.
                            # Record tombstone and DO NOT retry.
                            self._insert_tombstone("remote", rel, remote_item.get("token"), "remote_404")
                        else:
                            self._enqueue_retry(
                                "pull",
                                {"kind": "pull", "rel_path": rel, "remote_item": remote_item},
                                err,
                            )
                        summary["errors"] += 1
                    continue

            mappings = self._load_mappings()
            map_by_path = {m["local_rel_path"]: m for m in mappings}
            map_by_token = {m["remote_token"]: m for m in mappings if m.get("remote_token")}

            for rel, local_item in local_files.items():
                if rel in map_by_path:
                    continue

                remote_same_path = remote_by_path.get(rel)
                if remote_same_path and remote_same_path["token"] not in map_by_token:
                    try:
                        self._create_conflict_copy(rel, remote_same_path)
                        self._update_mapping(
                            rel_path=rel,
                            remote_token=remote_same_path["token"],
                            remote_type=remote_same_path.get("type") or "file",
                            local_hash=local_item["hash"],
                            remote_hash=remote_fingerprint(remote_same_path),
                            local_mtime=local_item["mtime"],
                            remote_modified_time=remote_same_path.get("modified_time", ""),
                            status="conflict",
                            conflict=1,
                        )
                        summary["conflicts"] += 1
                    except Exception as e:
                        self._enqueue_retry(
                            "pull",
                            {"kind": "pull", "rel_path": f"{rel}.remote_conflict_retry", "remote_item": remote_same_path},
                            str(e),
                        )
                        summary["errors"] += 1
                    continue

                try:
                    self._upload_local_file(rel, root_token)
                    summary["uploaded"] += 1
                except Exception as e:
                    self._enqueue_retry("upload", {"kind": "upload", "rel_path": rel}, str(e))
                    summary["errors"] += 1

            mappings = self._load_mappings()
            map_by_path = {m["local_rel_path"]: m for m in mappings}
            map_by_token = {m["remote_token"]: m for m in mappings if m.get("remote_token")}

            for remote_item in remote_files:
                if remote_item["token"] in map_by_token:
                    continue

                rel = safe_rel_path(remote_item["path"])
                if rel in map_by_path:
                    continue

                if rel in local_files:
                    try:
                        self._create_conflict_copy(rel, remote_item)
                        self._update_mapping(
                            rel_path=rel,
                            remote_token=remote_item["token"],
                            remote_type=remote_item.get("type") or "file",
                            local_hash=local_files[rel]["hash"],
                            remote_hash=remote_fingerprint(remote_item),
                            local_mtime=local_files[rel]["mtime"],
                            remote_modified_time=remote_item.get("modified_time", ""),
                            status="conflict",
                            conflict=1,
                        )
                        summary["conflicts"] += 1
                    except Exception as e:
                        self._enqueue_retry(
                            "pull",
                            {"kind": "pull", "rel_path": f"{rel}.remote_conflict_retry", "remote_item": remote_item},
                            str(e),
                        )
                        summary["errors"] += 1
                    continue

                try:
                    self._pull_remote_to_local(rel, remote_item)
                    summary["downloaded"] += 1
                except Exception as e:
                    err = str(e)
                    if "download_failed_status_404" in err:
                        self._insert_tombstone("remote", rel, remote_item.get("token"), "remote_404")
                    else:
                        self._enqueue_retry(
                            "pull",
                            {"kind": "pull", "rel_path": rel, "remote_item": remote_item},
                            err,
                        )
                        summary["errors"] += 1

            self._finish_sync_run(run_id, "success", summary)
            self._log("INFO", "sync", "run_success", json.dumps(summary, ensure_ascii=False))
            return summary

        except Exception as e:
            summary["errors"] += 1
            summary["fatal_error"] = str(e)
            self._finish_sync_run(run_id, "failed", summary)
            self._log("ERROR", "sync", "run_failed", json.dumps(summary, ensure_ascii=False))
            return summary
