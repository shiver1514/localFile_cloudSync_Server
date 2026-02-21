from __future__ import annotations

import json
import subprocess
from pathlib import Path

import typer
from rich import print
from rich.console import Console
from rich.table import Table

from app.core.config import DEFAULT_CONFIG_PATH, load_config, save_config

app = typer.Typer(add_completion=False)
console = Console()


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


@app.command()
def status():
    """Basic status (runtime paths, bind addr)."""
    cfg = load_config()
    table = Table(title="localFile_cloudSync_Server status")
    table.add_column("Key")
    table.add_column("Value")
    table.add_row("config", str(DEFAULT_CONFIG_PATH))
    table.add_row("local_root", cfg.sync.local_root)
    table.add_row("db", cfg.database.path)
    table.add_row("log", cfg.logging.file)
    table.add_row("web", f"http://{cfg.web_bind_host}:{cfg.web_port}")
    console.print(table)


@app.command("service-restart")
def service_restart():
    """Restart the Web UI service."""
    subprocess.check_call(["systemctl", "--user", "restart", "localfile-cloudsync.service"])
    print("OK")


@app.command("logs-tail")
def logs_tail(n: int = 200):
    """Tail service log file."""
    cfg = load_config()
    p = Path(cfg.logging.file)
    if not p.exists():
        print("")
        raise typer.Exit(0)
    lines = p.read_text(encoding="utf-8", errors="replace").splitlines()[-n:]
    print("\n".join(lines))


def main():
    app()


if __name__ == "__main__":
    main()
