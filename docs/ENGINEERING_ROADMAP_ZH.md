# localFile_cloudSync_Server 工程化落地路线（v1）

## 目标
- 从“可运行”升级到“可持续交付、可观测、可回滚、可运维”的工程化服务。

## 当前基线（2026-02-22）
- Web 控制台可用，CLI 可用，支持 OAuth 授权、手动同步、定时同步。
- systemd 用户服务可运行，日志与运行历史可查询。
- 已补充工程基础件：`Makefile`、`.github/workflows/ci.yml`、基础单元测试（`app/tests`）。
- 已补充健康检查：`/api/healthz`、`/api/readyz`。
- 已完成全量类型清债：`mypy app localfilesync` 可通过。
- 已补充发布与回滚脚本：`scripts/release.sh`、`scripts/rollback_release.sh`。

## 里程碑
### M2：质量基线（1-2 天）
- 建立代码质量门禁：`ruff` + `mypy` + `pytest`。
- 补充核心用例：配置校验、Token 流程、调度状态、run-once 行为。
- 统一错误码与 API 响应结构（成功/失败字段规范）。

### M3：交付基线（1-2 天）
- 增加 `Makefile` 或 `justfile`：`test`、`lint`、`run`、`build`、`release`。
- 固化部署脚本（systemd install/upgrade/restart/status）。
- 输出发布说明模板与回滚步骤模板。

### M4：运维基线（2-3 天）
- 指标化：同步耗时、上传/下载数量、错误率、调度延迟。
- 日志分级规范与关键事件打点（授权失败、接口限流、同步冲突）。
- 健康检查增强：增加 `/api/healthz` 与 `/api/readyz`。

### M5：安全与配置治理（1-2 天）
- 凭证管理改造：`.env` + 环境变量注入，避免明文进入仓库。
- 访问控制白名单策略文档化，最小权限化。
- 配置版本与迁移策略（配置 schema version）。

## 验收标准
- 新增/修改代码必须通过 lint + test。
- 发布前必须有可执行回滚步骤，且演练通过。
- 线上问题可通过日志与指标在 15 分钟内定位到模块级。

## 建议执行顺序
1. 先做 M2，补齐自动化质量门禁。
2. 再做 M3，让部署和回滚可重复。
3. 最后做 M4/M5，提升稳定性和安全性。
