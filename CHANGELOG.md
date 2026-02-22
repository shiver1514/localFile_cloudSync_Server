# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog and this project uses Semantic Versioning.

## [Unreleased]

### Added

- 发布工程化基础：`Makefile`、CI、健康检查接口、基础测试。

### Changed

- Web 控制台增强（连接状态、自动同步倒计时、异常详情入口、异常清空）。

### Fixed

- 修复“异常 run_id 与异常条数”易混淆文案，统一为“第X次（异常/成功）”。
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
