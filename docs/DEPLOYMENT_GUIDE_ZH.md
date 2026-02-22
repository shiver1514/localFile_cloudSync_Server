# 安装部署与开机自启手册（ZH）

本文覆盖 `localFile_cloudSync_Server` 的安装、初始化配置、服务化部署、开机自启、升级回滚与常见故障排查。

## 1. 适用范围

- 操作系统：Linux（需支持 `systemd --user`）
- 默认仓库路径：`/home/n150/openclaw_workspace/localFile_cloudSync_Server`
- 服务名：`localfile-cloudsync.service`

如果你的仓库路径不是上面的默认值，先同步修改以下文件中的绝对路径：

- `deploy/systemd/localfile-cloudsync.service`
- `scripts/switch_m1_service.sh`

## 2. 安装与依赖

在仓库根目录执行：

```bash
cd /home/n150/openclaw_workspace/localFile_cloudSync_Server
python3 -m venv venv
source venv/bin/activate
python -m pip install -U pip
make install
```

说明：

- `make install` 会安装 `app/pyproject.toml` 中的运行依赖与开发依赖。
- 后续所有 CLI/Web 命令都建议在该虚拟环境中执行。

## 3. 初始配置与授权

### 3.1 配置文件创建与检查

- 默认配置文件路径：`config.yaml`
- `config.yaml` 为本机配置文件，已在 `.gitignore` 中忽略，不参与版本控制。
- 仓库提供配置示例：`config.yaml.example`。
- 如果配置文件不存在，程序在首次加载配置时会自动创建（也可手动复制示例文件）。

可选初始化命令（不覆盖已有本机配置）：

```bash
cp -n config.yaml.example config.yaml
```

可通过以下命令触发配置加载并检查内容：

```bash
cd app
python -m localfilesync.cli.main config-show
```

### 3.2 写入飞书凭据

建议使用 CLI 写入，不要把真实密钥提交到仓库：

```bash
cd app
python -m localfilesync.cli.main config-set-auth \
  --app-id "<YOUR_APP_ID>" \
  --app-secret "<YOUR_APP_SECRET>" \
  --user-token-file "/home/n150/openclaw_workspace/localFile_cloudSync_Server/runtime/user_tokens.json"
```

### 3.3 完成 OAuth 用户授权

1. 生成授权链接：

```bash
cd app
python -m localfilesync.cli.main auth-url
```

2. 浏览器完成授权后拿到 `code`。
3. 回填 `code` 换取并保存用户令牌：

```bash
cd app
python -m localfilesync.cli.main auth-exchange --code "<OAUTH_CODE>"
```

### 3.4 同步配置最小检查项

请确认 `config.yaml` 至少包含有效值：

- `sync.remote_folder_token`
- `sync.default_sync_direction`（可选：`remote_wins`/`local_wins`/`bidirectional`）
- `sync.poll_interval_sec`（`0` 为关闭自动同步，`>0` 为自动轮询秒数）
- `sync.remote_delete_mode`（`recycle_bin` 或 `hard_delete`）
- `sync.cleanup_empty_remote_dirs`（`true` 时清理远端空目录）
- `sync.cleanup_remote_missing_dirs_recursive`（`true` 时可递归删除远端缺失目录）

运行配置校验：

```bash
cd app
python -m localfilesync.cli.main config-validate --strict
```

### 3.5 飞书事件订阅（推荐开启，降低轮询延迟）

应用支持事件回调触发同步：

- 回调接口：`POST /api/events/feishu`
- 状态接口：`GET /api/status/event-callback`

配置建议（`config.yaml`）：

```yaml
sync:
  event_callback_enabled: true
  event_verify_token: "<YOUR_VERIFY_TOKEN>"
  event_encrypt_key: ""
  event_debounce_sec: 15
  event_trigger_types:
  - drive.file.edit_v1
  - drive.file.title_updated_v1
  - drive.file.created_in_folder_v1
  - drive.file.deleted_v1
  - drive.file.trashed_v1
```

注意：

- 回调地址必须是飞书可访问的公网 HTTPS 地址（反向代理到本服务）。
- `event_verify_token` 需与飞书后台配置一致。
- 若设置了 `event_encrypt_key`，需安装 `pycryptodome`（项目依赖已包含）。
- 建议保留 `sync.poll_interval_sec` 作为兜底，事件回调仅用于加速。

## 4. 首次运行验证

### 4.1 本地前置检查（不访问远端）

```bash
cd app
python -m localfilesync.cli.main run-once --dry-run
```

### 4.2 Web 面板前台运行

```bash
cd app
python -m localfilesync.web.main
```

健康检查：

```bash
curl -fsS http://127.0.0.1:8765/api/healthz
curl -fsS http://127.0.0.1:8765/api/readyz
```

## 5. systemd 用户态部署

### 5.1 推荐方式（脚本）

```bash
cd /home/n150/openclaw_workspace/localFile_cloudSync_Server
scripts/switch_m1_service.sh prepare
scripts/switch_m1_service.sh status
```

`prepare` 会执行：

- 复制服务单元到 `~/.config/systemd/user/localfile-cloudsync.service`
- `systemctl --user daemon-reload`
- `systemctl --user enable --now localfile-cloudsync.service`

### 5.2 手动方式

```bash
mkdir -p ~/.config/systemd/user
cp /home/n150/openclaw_workspace/localFile_cloudSync_Server/deploy/systemd/localfile-cloudsync.service \
  ~/.config/systemd/user/localfile-cloudsync.service
systemctl --user daemon-reload
systemctl --user enable --now localfile-cloudsync.service
```

## 6. 开机自启配置

仅 `enable` 能保证“登录后自动启动”；若要“开机后即使未登录也保持用户服务可运行”，还需要开启 linger：

```bash
systemctl --user enable localfile-cloudsync.service
loginctl enable-linger "$USER"
loginctl show-user "$USER" -p Linger
```

期望输出包含 `Linger=yes`。

## 7. 日常运维命令

状态查看：

```bash
systemctl --user status localfile-cloudsync.service --no-pager
cd /home/n150/openclaw_workspace/localFile_cloudSync_Server/app
python -m localfilesync.cli.main service-status
python -m localfilesync.cli.main status
```

重启服务：

```bash
systemctl --user restart localfile-cloudsync.service
```

查看日志：

```bash
journalctl --user -u localfile-cloudsync.service -n 200 --no-pager
cd /home/n150/openclaw_workspace/localFile_cloudSync_Server/app
python -m localfilesync.cli.main logs-tail --n 200
```

## 8. 升级与回滚

### 8.1 升级（部署机常规）

```bash
cd /home/n150/openclaw_workspace/localFile_cloudSync_Server
git pull
source venv/bin/activate
make install
systemctl --user restart localfile-cloudsync.service
```

### 8.2 发布流程（版本号与标签）

参考：`docs/RELEASE_PLAYBOOK_ZH.md`

常用命令：

```bash
cd /home/n150/openclaw_workspace/localFile_cloudSync_Server
scripts/release.sh --dry-run --bump patch
scripts/release.sh --bump patch
```

### 8.3 回滚到指定版本

```bash
cd /home/n150/openclaw_workspace/localFile_cloudSync_Server
scripts/rollback_release.sh --target vX.Y.Z --restart-service
```

## 9. 常见问题排查

`systemctl --user` 不可用：

- 当前 shell 不是用户态 systemd 环境；需在支持 `systemd --user` 的会话执行。

服务启动后立即退出：

- 先看 `journalctl --user -u localfile-cloudsync.service`。
- 检查服务单元中的 `WorkingDirectory`、`ExecStart` 与实际路径是否一致。

同步未执行：

- 检查 `sync.poll_interval_sec` 是否为 `0`。
- 检查 `sync.remote_folder_token` 是否为空。
- 用 `python -m localfilesync.cli.main run-once` 看单次同步输出。

鉴权失败或 401：

- 重新执行 `auth-url` + `auth-exchange`。
- 或执行 `python -m localfilesync.cli.main auth-refresh --force` 更新令牌。

重启机器后服务未自动起来：

- 执行 `systemctl --user is-enabled localfile-cloudsync.service`。
- 执行 `loginctl show-user "$USER" -p Linger`，确保 `Linger=yes`。
