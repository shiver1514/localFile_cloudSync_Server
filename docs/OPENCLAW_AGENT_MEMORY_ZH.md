# OpenClaw 项目记忆（localFile_cloudSync_Server）

本文件用于给 OpenClaw/Coding Agent 提供长期、稳定、可执行的项目上下文。  
目标：新会话冷启动时，能快速进入正确操作轨道，减少重复试错。

## 1. 项目定位

- 项目名称：`localFile_cloudSync_Server`
- 当前阶段：可用产品 + 工程化基线已落地
- 核心能力：
  - 飞书 Drive 文件型同步（本地 <-> 云端）
  - CLI 调试与运维
  - Web 控制台（配置、树查看、状态、日志）
  - 定时同步调度（scheduler）
  - 发布/回滚脚本与基础 CI

## 2. 代码与目录边界

- 业务主代码：`app/app/`
- 兼容入口：`app/localfilesync/`
- 配置文件：`config.yaml`
- 运行态目录：`runtime/`
- 运维脚本：`scripts/`
- 发布文档：`docs/releases/`

关键约束：
- `sync.local_root` 运行时会被强制锁定到固定目录（见 `app/app/core/config.py`）。
- 运行态数据库与日志在服务目录 `runtime/` 下，不应落到业务同步目录中。

## 3. 用户偏好与产品要求（高优先级）

- 以中文沟通为主。
- 优先“可执行结果”，少空泛描述。
- UI 要求：
  - 状态可视化明显（例如呼吸灯 + 文本）
  - 所有按钮要有明确交互反馈（loading/success/fail）
  - 异常必须可快速定位（可直接跳日志并带过滤条件）
- CLI 与 Web 都要可独立完成关键操作（授权、状态检查、同步触发）。

## 4. 当前架构要点

### 4.1 鉴权与飞书连接

- 当前版本仅支持飞书云空间，且仅支持 `user_access`（`user_access_token`）链路。
- 使用飞书 OAuth 用户令牌流：
  - `auth-url` 生成授权链接
  - `auth-exchange` 换取 token
  - `auth-refresh` 刷新 token
- 连接状态接口：`GET /api/status/feishu`

### 4.2 同步引擎

- 主要实现：`app/app/providers/feishu_legacy/sync_engine.py`
- 支持：
  - 初始同步策略
  - 重命名/移动处理
  - 冲突策略（keep_both 等）
  - 重试队列
  - 摘要统计（uploaded/downloaded/errors 等）

### 4.3 调度器

- 后端 scheduler 在应用生命周期启动/停止。
- 核心状态接口：`GET /api/status/scheduler`
- `poll_interval_sec=0` 表示禁用自动同步。

### 4.4 Web 控制台

- 页面代码：`app/app/web/pages.py`
- API：`app/app/web/api.py`
- 必备可观测能力：
  - 飞书连接状态
  - Service 状态
  - 自动同步状态与倒计时
  - 最近同步摘要
  - 日志过滤查看（level/module）

## 5. 关键运维命令（标准）

环境准备：

```bash
cd /home/n150/openclaw_workspace/localFile_cloudSync_Server
source venv/bin/activate
```

质量门禁：

```bash
make check
```

服务健康：

```bash
curl -fsS http://127.0.0.1:8765/api/healthz
curl -fsS http://127.0.0.1:8765/api/readyz
```

发布/回滚：

```bash
scripts/release.sh --bump patch
scripts/rollback_release.sh --target vX.Y.Z
```

## 6. 开发守则（给 Agent）

- 修改前先确认范围，避免触碰无关目录。
- 不在业务改动中引入破坏性重构。
- 每次功能完成后最少执行：
  - `ruff`
  - `mypy`
  - `pytest`
  - 关键 API smoke（healthz/readyz）
- 新增用户可见能力时，必须同步更新：
  - `README.md`
  - 对应发布说明/变更日志

## 7. 常见问题与排查

- 问题：按钮点击无反馈
  - 排查：前端按钮绑定是否失效，API 是否返回错误，`logs` 面板是否有报错
- 问题：“最近同步异常”看不到详情
  - 排查：查看日志过滤条件是否只筛 `ERROR`，必要时切换 `WARNING + module=sync`
- 问题：自动同步没跑
  - 排查：`poll_interval_sec` 是否为 0，`/api/status/scheduler` 的 `enabled/running` 状态

## 8. 后续演进建议（下一阶段）

- 指标化与告警：同步耗时、错误率、调度延迟。
- 安全治理：敏感配置环境变量化。
- provider 抽象扩展：在不破坏现有飞书实现的前提下接入新云端。

---

维护说明：
- 本文档是 OpenClaw 的“长期记忆源”。
- 当架构、命令、流程发生变化时，优先更新本文件，再更新其他说明文档。
