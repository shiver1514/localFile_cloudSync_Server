#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="$ROOT_DIR/app"
PY_BIN="$ROOT_DIR/venv/bin/python"
RUNTIME_DIR="$ROOT_DIR/runtime"
mkdir -p "$RUNTIME_DIR"

default_target_ts() {
  local now_h
  now_h="$(date +%H)"
  if ((10#$now_h < 8)); then
    date -d "today 08:00" +%s
  else
    date -d "tomorrow 08:00" +%s
  fi
}

TARGET_TS="${1:-$(default_target_ts)}"
INTERVAL_SEC="${INTERVAL_SEC:-600}"
SAMPLE_TEST_EVERY="${SAMPLE_TEST_EVERY:-3}"
LOG_FILE="${LOG_FILE:-$RUNTIME_DIR/overnight_autopilot_$(date +%Y%m%d_%H%M%S).log}"
STATUS_JSON="$RUNTIME_DIR/overnight_autopilot_status.json"
PID_FILE="$RUNTIME_DIR/overnight_autopilot.pid"

echo "$$" > "$PID_FILE"

log() {
  local ts
  ts="$(date '+%F %T')"
  echo "[$ts] $*" | tee -a "$LOG_FILE"
}

write_status() {
  local now
  now="$(date '+%F %T')"
  cat > "$STATUS_JSON" <<EOF
{
  "pid": $$,
  "updated_at": "$now",
  "target_ts": $TARGET_TS,
  "interval_sec": $INTERVAL_SEC,
  "log_file": "$LOG_FILE"
}
EOF
}

http_check() {
  local url="$1"
  local out="$2"
  curl -sS --max-time 12 -o "$out" -w '%{http_code}' "$url" 2>/dev/null || echo "000"
}

json_eval() {
  local file="$1"
  local expr="$2"
  "$PY_BIN" - "$file" "$expr" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
expr = sys.argv[2]
if not path.exists():
    print("")
    raise SystemExit(0)
try:
    payload = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    print("")
    raise SystemExit(0)

cur = payload
for part in expr.split("."):
    if not part:
        continue
    if isinstance(cur, dict):
        cur = cur.get(part)
    else:
        cur = None
        break
if cur is None:
    print("")
elif isinstance(cur, bool):
    print("true" if cur else "false")
else:
    print(str(cur))
PY
}

restart_service() {
  if systemctl --user restart localfile-cloudsync.service >> "$LOG_FILE" 2>&1; then
    log "service_restart: ok"
  else
    log "service_restart: failed"
  fi
}

run_sample_tests() {
  (
    cd "$APP_DIR"
    "$PY_BIN" -m pytest tests/test_api_health.py tests/test_event_callback.py -q
  ) >> "$LOG_FILE" 2>&1 && log "sample_tests: pass" || log "sample_tests: failed"
}

scan_logs() {
  local hits
  hits="$(tail -n 500 "$RUNTIME_DIR/service.log" 2>/dev/null | rg -n "ERROR|run_failed|fatal_error|Traceback|exception" -S || true)"
  if [[ -n "$hits" ]]; then
    log "log_scan: suspicious_lines_detected"
    echo "$hits" | tail -n 20 >> "$LOG_FILE"
  else
    log "log_scan: clean"
  fi
}

log "autopilot_start target_ts=$TARGET_TS interval_sec=$INTERVAL_SEC sample_test_every=$SAMPLE_TEST_EVERY"

cycle=0
while true; do
  now_ts="$(date +%s)"
  if (( now_ts >= TARGET_TS )); then
    break
  fi
  cycle=$((cycle + 1))
  write_status

  tmp_health="$RUNTIME_DIR/.autopilot_health.json"
  tmp_ready="$RUNTIME_DIR/.autopilot_ready.json"
  tmp_sched="$RUNTIME_DIR/.autopilot_scheduler.json"
  tmp_event="$RUNTIME_DIR/.autopilot_event.json"

  health_code="$(http_check "http://127.0.0.1:8765/api/healthz" "$tmp_health")"
  ready_code="$(http_check "http://127.0.0.1:8765/api/readyz" "$tmp_ready")"
  sched_code="$(http_check "http://127.0.0.1:8765/api/status/scheduler" "$tmp_sched")"
  event_code="$(http_check "http://127.0.0.1:8765/api/status/event-callback" "$tmp_event")"

  sched_enabled="$(json_eval "$tmp_sched" "enabled")"
  sched_running="$(json_eval "$tmp_sched" "running")"
  sched_last_result="$(json_eval "$tmp_sched" "last_result")"
  event_enabled="$(json_eval "$tmp_event" "enabled")"
  event_verify_token_configured="$(json_eval "$tmp_event" "verify_token_configured")"
  event_last_result="$(json_eval "$tmp_event" "last_result")"
  event_pending="$(json_eval "$tmp_event" "pending")"

  log "cycle=$cycle health=$health_code ready=$ready_code scheduler=$sched_code(auto_sync_enabled=$sched_enabled,running=$sched_running,last=$sched_last_result) event=$event_code(enabled=$event_enabled,token=$event_verify_token_configured,last=$event_last_result,pending=$event_pending)"

  need_restart="false"
  if [[ "$health_code" != "200" || "$ready_code" != "200" ]]; then
    need_restart="true"
    log "autofix_trigger: health_or_ready_not_ok"
  fi
  if [[ "$sched_enabled" == "true" && "$sched_running" != "true" ]]; then
    need_restart="true"
    log "autofix_trigger: scheduler_enabled_but_not_running"
  fi
  if [[ "$event_enabled" == "true" && "$event_verify_token_configured" != "true" ]]; then
    log "config_warn: event_callback_enabled_but_verify_token_missing"
  fi

  if [[ "$need_restart" == "true" ]]; then
    restart_service
  fi

  if (( cycle % SAMPLE_TEST_EVERY == 0 )); then
    run_sample_tests
  fi

  scan_logs
  sleep "$INTERVAL_SEC"
done

write_status
log "autopilot_done"
rm -f "$PID_FILE"
