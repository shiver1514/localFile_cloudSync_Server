# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog and this project uses Semantic Versioning.

## [Unreleased]

### Added

- 暂无。

### Changed

- 暂无。

### Fixed

- 暂无。

## [v0.2.3] - 2026-02-23

### Added

- 调度状态新增 `initialized` 语义，区分“未初始化”与“已关闭自动同步”。
- 增加事件回调误配置保护：`event_callback_enabled=true` 且 `event_verify_token` 为空时，回调接口返回 `503 event_verify_token_missing`。
- 增加相关回归测试：`app/tests/test_api_health.py`、`app/tests/test_event_callback.py`。

### Changed

- Web 控制台优化：
  - 调度器未初始化阶段统一显示“获取中”，避免首屏闪现“关闭/失败”。
  - “最近同步”在执行中优先显示“执行中”状态。
  - 优化视觉层次与动效（卡片、标签、按钮、面板切换、移动端 sticky tabs 降级）。
- FastAPI 应用版本改为读取包元数据，避免硬编码版本号漂移。
- `Makefile` 拆分 `ROOT_PYTHON` / `APP_PYTHON`，兼容仓库根目录虚拟环境。
- 夜间巡检脚本 `scripts/overnight_autopilot.sh` 优化目标时间与状态日志字段。

### Fixed

- 修复 `make check` 在根目录虚拟环境场景下 Python 路径错误。
- 修复调度器单轮异常可能导致循环退出的问题，改为记录错误并继续下一轮。
- 修复 UI 首次加载时自动同步状态误判为“关闭”的体验问题。

## [v0.2.2] - 2026-02-22

### Added

- 飞书事件回调触发同步：
  - `POST /api/events/feishu`
  - `GET /api/status/event-callback`
- 事件处理能力：去抖、去重、并发保护、白名单匹配、可选密文解密与签名校验。
- CLI 增加事件回调状态查询，前端新增事件回调配置与状态面板。
- 新增事件回调测试：`app/tests/test_event_callback.py`。

### Changed

- 同步架构升级为“轮询兜底 + 事件触发加速”双轨模式。
- 文档补充事件回调配置、部署及 FAQ 说明。

### Fixed

- 修复回调高频场景下重复触发导致的并发冲突风险。

## [v0.2.1] - 2026-02-22

### Added

- 双向同步策略 `bidirectional` 正式落地，支持按变化侧自动决策上传/下载/删除。
- 配置与文档完善：
  - `config.yaml` 改为本机文件（`.gitignore`），新增 `config.yaml.example`。
  - 新增安装部署与开机自启手册：`docs/DEPLOYMENT_GUIDE_ZH.md`。
- 新增双向策略回归测试：`app/tests/test_sync_direction_bidirectional.py`。

### Changed

- 同步引擎增强：本地文件 SHA256 + 远端指纹参与比对，冲突场景按时间戳决策并支持重试。
- Web 控制台增强加载态与配置区展示，减少“失败/未开始”误读。
- README 与文档索引补充环境依赖、部署路径和策略说明。

### Fixed

- 修复“清空最近异常”导致摘要被误清空的问题，改为仅清错不清记录。
- 修复部分状态接口文案与页面表达不一致问题。

## [v0.2.0] - 2026-02-22

### Added

- 工程化基础：`Makefile`、`.github/workflows/ci.yml`、基础单元测试。
- 健康检查接口：`/api/healthz`、`/api/readyz`。
- 发布与回滚脚本：`scripts/release.sh`、`scripts/rollback_release.sh`。

### Changed

- UI 控制台重构：交互反馈、自动同步状态、异常详情入口、异常清空按钮。
- CLI 能力扩展：`config-validate`、`service-status`、`logs-tail` 过滤、`run-once`。
- 全量类型检查通过：`mypy app localfilesync`。

### Fixed

- 修复“最近同步异常”展示语义歧义（`run_id` 与异常条数混淆）。
- 修复异常详情查看默认筛选不命中 `WARNING sync` 日志的问题。
