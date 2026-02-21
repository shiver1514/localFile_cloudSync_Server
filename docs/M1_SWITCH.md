# M1 Service Switch Guide

This repository now ships:

- new unit template: `deploy/systemd/localfile-cloudsync.service`
- helper script: `scripts/switch_m1_service.sh`

## 1) Prepare M1 web service (non-destructive)

```bash
cd /home/n150/openclaw_workspace/localFile_cloudSync_Server
scripts/switch_m1_service.sh prepare
scripts/switch_m1_service.sh status
```

`prepare` starts `localfile-cloudsync.service` and **does not stop/disable**
`openclaw-feishu-sync.service`.

## 2) Validate endpoints

- `GET /api/config`
- `GET /api/logs`
- `GET /api/status/feishu`
- `POST /api/actions/run-once`

## 3) Cutover later (manual)

When you are ready to retire the old daemon:

```bash
scripts/switch_m1_service.sh cutover
```

Rollback old service if needed:

```bash
scripts/switch_m1_service.sh rollback
```

