# localFile_cloudSync_Server / app

This is the next-generation implementation (CLI + Web UI) of the sync service.

## Run (no PYTHONPATH hack)

```bash
cd ~/openclaw_workspace/localFile_cloudSync_Server
source venv/bin/activate
cd app
python -m localfilesync.cli.main status
python -m localfilesync.web.main
```

## Optional editable install

```bash
cd ~/openclaw_workspace/localFile_cloudSync_Server
source venv/bin/activate
python -m pip install -e app --no-build-isolation
```

After editable install, console scripts are available:

```bash
localfilesync-cli status
localfilesync-web
```

## systemd user service (M1)

Template unit:

- `deploy/systemd/localfile-cloudsync.service`

Switch helper script (non-destructive by default):

- `scripts/switch_m1_service.sh prepare`
- `scripts/switch_m1_service.sh status`

`prepare` intentionally does not stop/disable `openclaw-feishu-sync.service`.

## Engineering quick check

From repo root:

```bash
make check
```

API probes:

```bash
curl -fsS http://127.0.0.1:8765/api/healthz
curl -fsS http://127.0.0.1:8765/api/readyz
```

Release/rollback scripts:

```bash
./scripts/release.sh --help
./scripts/rollback_release.sh --help
```
