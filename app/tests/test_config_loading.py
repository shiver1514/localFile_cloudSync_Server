from pathlib import Path

from app.core import config as config_module


def test_load_config_creates_from_template(monkeypatch, tmp_path: Path):
    template = tmp_path / "config.yaml.example"
    target = tmp_path / "config.yaml"
    runtime_dir = tmp_path / "runtime"
    template.write_text(
        "\n".join(
            [
                "auth:",
                "  app_id: tpl_app_id",
                "  app_secret: tpl_app_secret",
                "  user_token_file: /tmp/user_tokens.json",
                "sync:",
                "  local_root: /tmp/local_root",
                "logging:",
                f"  file: {runtime_dir / 'service.log'}",
                "database:",
                f"  path: {runtime_dir / 'service.db'}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_TEMPLATE_PATH", template)
    monkeypatch.setattr(config_module, "ensure_runtime_dirs", lambda _cfg: None)

    cfg = config_module.load_config(target)

    assert target.exists()
    assert cfg.auth.app_id == "tpl_app_id"
    assert cfg.auth.app_secret == "tpl_app_secret"
    assert cfg.sync.local_root == "/tmp/local_root"


def test_load_config_creates_defaults_when_template_missing(monkeypatch, tmp_path: Path):
    target = tmp_path / "config.yaml"
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_TEMPLATE_PATH", tmp_path / "missing-template.yaml")
    monkeypatch.setattr(config_module, "ensure_runtime_dirs", lambda _cfg: None)

    cfg = config_module.load_config(target)

    assert target.exists()
    assert cfg.sync.default_sync_direction == "remote_wins"


def test_load_config_falls_back_when_template_invalid(monkeypatch, tmp_path: Path):
    template = tmp_path / "config.yaml.example"
    target = tmp_path / "config.yaml"
    template.write_text("auth: [invalid\n", encoding="utf-8")
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_TEMPLATE_PATH", template)
    monkeypatch.setattr(config_module, "ensure_runtime_dirs", lambda _cfg: None)

    cfg = config_module.load_config(target)

    assert target.exists()
    assert cfg.sync.default_sync_direction == "remote_wins"
