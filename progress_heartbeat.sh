#!/usr/bin/env bash
set -euo pipefail

STATUS_FILE="/home/n150/openclaw_workspace/localFile_cloudSync_Server/runtime/progress.json"
LAST_CMD_FILE="/home/n150/openclaw_workspace/localFile_cloudSync_Server/runtime/last_cmd.txt"
SEQ_FILE="/home/n150/openclaw_workspace/localFile_cloudSync_Server/runtime/heartbeat_seq.txt"
LOG_FILE="/home/n150/openclaw_workspace/localFile_cloudSync_Server/runtime/heartbeat.log"

export PATH="/home/n150/.npm-global/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

exec >>"$LOG_FILE" 2>&1

echo "----- $(date '+%F %T') heartbeat start -----"

# monotonic seq to prove change every time
seq=0
if [[ -f "$SEQ_FILE" ]]; then
  seq=$(cat "$SEQ_FILE" | tr -dc '0-9' || echo 0)
fi
seq=$((seq+1))
echo "$seq" > "$SEQ_FILE"

json_get() {
  local key="$1"
  python3 - <<PY
import json
p='$STATUS_FILE'
try:
  with open(p,'r',encoding='utf-8') as f:
    d=json.load(f)
  print(d.get('$key',''))
except FileNotFoundError:
  print('')
PY
}

pct=$(json_get percent)
phase=$(json_get phase)
eta=$(json_get eta)
note=$(json_get note)

last_cmd=""
if [[ -f "$LAST_CMD_FILE" ]]; then
  last_cmd=$(tail -n 1 "$LAST_CMD_FILE" | sed 's/^\s\+//; s/\s\+$//')
fi

now=$(date '+%F %T')
msg="[开发心跳 #${seq}] localFile_cloudSync_Server\n- 时间：${now}\n- 进度：${pct}%\n- 当前：${phase}\n- ETA：${eta}\n- 备注：${note}"
if [[ -n "$last_cmd" ]]; then
  msg+="\n- 最新指令：${last_cmd}"
fi

echo "sending via $(command -v openclaw || echo 'openclaw_missing')"
openclaw message send --channel feishu --target "user:ou_7aa2f86c590a59fe4888212fd0320d5a" --message "$msg"
echo "sent ok"
