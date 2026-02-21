#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/n150/openclaw_workspace/localFile_cloudSync_Server"
UNIT_SRC="$ROOT/deploy/systemd/localfile-cloudsync.service"
UNIT_DST="$HOME/.config/systemd/user/localfile-cloudsync.service"

usage() {
  cat <<'EOF'
Usage:
  scripts/switch_m1_service.sh prepare
  scripts/switch_m1_service.sh status
  scripts/switch_m1_service.sh cutover
  scripts/switch_m1_service.sh rollback

What each mode does:
  prepare: install/start localfile-cloudsync.service
           (does NOT stop/disable openclaw-feishu-sync.service)
  status:  show both service states
  cutover: stop+disable old openclaw service (manual confirmation required)
  rollback: re-enable old openclaw service
EOF
}

require_systemd_user() {
  if ! systemctl --user --version >/dev/null 2>&1; then
    echo "systemd --user is not available in this shell."
    exit 1
  fi
}

cmd="${1:-}"
case "$cmd" in
  prepare)
    require_systemd_user
    mkdir -p "$HOME/.config/systemd/user"
    cp "$UNIT_SRC" "$UNIT_DST"
    systemctl --user daemon-reload
    systemctl --user enable --now localfile-cloudsync.service
    echo "Prepared M1 service. Old openclaw-feishu-sync.service was NOT changed."
    ;;
  status)
    require_systemd_user
    systemctl --user status localfile-cloudsync.service --no-pager || true
    systemctl --user status openclaw-feishu-sync.service --no-pager || true
    ;;
  cutover)
    require_systemd_user
    systemctl --user stop openclaw-feishu-sync.service
    systemctl --user disable openclaw-feishu-sync.service
    echo "Old openclaw service disabled."
    ;;
  rollback)
    require_systemd_user
    systemctl --user enable --now openclaw-feishu-sync.service
    echo "Old openclaw service re-enabled."
    ;;
  *)
    usage
    exit 1
    ;;
esac
