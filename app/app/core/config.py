from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

FIXED_LOCAL_ROOT = str(Path("/home/n150/openclaw_workspace/search_docs"))


class FeishuAuthConfig(BaseModel):
    app_id: str = ""
    app_secret: str = ""
    user_token_file: str = ""
    timeout_sec: int = 30


class SyncConfig(BaseModel):
    local_root: str = FIXED_LOCAL_ROOT
    remote_folder_token: str = ""
    poll_interval_sec: int = 300
    default_sync_direction: str = "remote_wins"
    initial_sync_strategy: str = "local_wins"
    remote_recycle_bin: str = "SyncRecycleBin"
    local_trash_dir: str = ".sync_trash"
    exclude_dirs: list[str] = Field(default_factory=lambda: [
        ".git",
        ".sync_trash",
        ".sync_quarantine",
        ".local_state",
        "__pycache__",
    ])


class LoggingConfig(BaseModel):
    level: str = "INFO"
    file: str = str(Path("/home/n150/openclaw_workspace/localFile_cloudSync_Server/runtime/service.log"))


class DatabaseConfig(BaseModel):
    path: str = str(Path("/home/n150/openclaw_workspace/localFile_cloudSync_Server/runtime/service.db"))


class AppConfig(BaseModel):
    auth: FeishuAuthConfig = Field(default_factory=FeishuAuthConfig)
    sync: SyncConfig = Field(default_factory=SyncConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)

    # Web UI
    web_bind_host: str = "127.0.0.1"  # can be set to LAN IP
    web_port: int = 8765


PROJECT_ROOT = Path("/home/n150/openclaw_workspace/localFile_cloudSync_Server")
RUNTIME_DIR = PROJECT_ROOT / "runtime"
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.yaml"
LAST_RUN_ONCE_PATH = RUNTIME_DIR / "last_run_once.json"


def _normalize_local_root(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    try:
        return str(Path(raw).expanduser().resolve(strict=False))
    except Exception:
        return str(Path(raw).expanduser())


FIXED_LOCAL_ROOT_NORMALIZED = _normalize_local_root(FIXED_LOCAL_ROOT)


def is_local_root_in_scope(value: str) -> bool:
    return _normalize_local_root(value) == FIXED_LOCAL_ROOT_NORMALIZED


def enforce_local_root_scope(cfg: AppConfig) -> tuple[bool, str]:
    requested = cfg.sync.local_root
    if not is_local_root_in_scope(requested):
        cfg.sync.local_root = FIXED_LOCAL_ROOT
        return True, requested

    # Keep a canonical value in-memory to avoid path aliasing.
    cfg.sync.local_root = FIXED_LOCAL_ROOT
    return False, requested


def ensure_runtime_dirs(cfg: AppConfig):
    Path(cfg.logging.file).parent.mkdir(parents=True, exist_ok=True)
    Path(cfg.database.path).parent.mkdir(parents=True, exist_ok=True)


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> AppConfig:
    import yaml

    if not path.exists():
        cfg = AppConfig()
        ensure_runtime_dirs(cfg)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(cfg.model_dump(), allow_unicode=True, sort_keys=False), encoding="utf-8")
        return cfg

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    cfg = AppConfig.model_validate(data)
    ensure_runtime_dirs(cfg)
    return cfg


def save_config(cfg: AppConfig, path: Path = DEFAULT_CONFIG_PATH):
    import yaml

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(cfg.model_dump(), allow_unicode=True, sort_keys=False), encoding="utf-8")
