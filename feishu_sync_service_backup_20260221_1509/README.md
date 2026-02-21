# feishu_sync_service

独立后台服务（与 OpenClaw 解耦），用于本地目录与飞书云空间的双向同步。

## 当前能力（MVP）

- 本地 `~/openclaw_workspace/search_docs/` ↔ 飞书云空间根目录（可改 `remote_folder_token`）
- 双向新增/修改/重命名
- 删除采用软删除：
  - 本地移入 `.sync_trash/`
  - 飞书移入 `SyncRecycleBin`
- 冲突策略：保留两份（本地生成 `*.remote_conflict_时间戳`）
- SQLite 映射与重试队列
- 后台轮询 + 手动一键同步

## 运行方式

```bash
cd /home/n150/openclaw_workspace/feishu_sync_service

# 手动执行一次同步
python3 app.py run-once

# 查看状态
python3 app.py status

# 常驻后台（前台运行）
python3 app.py daemon
```

## systemd（推荐 24h 运行）

服务文件：`openclaw-feishu-sync.service`

```bash
mkdir -p ~/.config/systemd/user
cp /home/n150/openclaw_workspace/feishu_sync_service/openclaw-feishu-sync.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now openclaw-feishu-sync.service
systemctl --user status openclaw-feishu-sync.service
```

## cron（可选）

如果你更偏好 cron，可按固定周期触发：

```bash
crontab -e
# 每 5 分钟执行一次
*/5 * * * * /usr/bin/python3 /home/n150/openclaw_workspace/feishu_sync_service/app.py run-once >> /home/n150/openclaw_workspace/feishu_sync_service/logs/cron.log 2>&1
```

## 配置

编辑 `config.yaml`：

- `auth.app_id` / `auth.app_secret`（用于 token 刷新；可留空并通过 `auth.env_file` 自动读取）
- `auth.user_token_file`（用户授权 token 文件）
- `auth.env_file`（可选，`FEISHU_APP_ID`/`FEISHU_APP_SECRET` 来源）
- `sync.local_root`（本地同步根目录）
- `sync.remote_folder_token`（空字符串表示飞书根目录）
- `sync.poll_interval_sec`（轮询间隔）

## 数据与日志

- 数据库：`data/service.db`
- 运行日志：`logs/service.log`
- 同步流水：`logs/sync-YYYYMMDD.jsonl`

## 认证优先级

默认：`user_access_token` > `tenant_access_token`
