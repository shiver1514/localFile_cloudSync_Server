# localFile_cloudSync_Server

目标：把现有 `feishu_sync_service` 演进为一个“完整工程化”的本地↔云端（飞书/未来钉钉）同步服务应用。

- 备份：`feishu_sync_service_backup_20260221_1509/`
- 新实现（即将创建）：`app/`（或 `server/`）目录

## 需求摘要（Shiver）

1. CLI 调试界面 + Web 配置/调试界面（交互友好）
2. Linux 后台静默启动（systemd --user），可配置定时刷新
3. 配置项：
   - 飞书 app_id/app_secret
   - user token / refresh token 查看与修改
   - 飞书连接状态查看
   - 本地目录配置/查看
   - 使用文档查看
   - 本地数据库查看
4. 详细日志系统：分级、可按文档/模块检索；OpenClaw 可查看服务运行情况
5. 云端接口可替换：飞书 → 钉钉（保留 provider 抽象）

## 下一步

- 定义项目结构与接口抽象（provider / sync engine / storage / web ui）
- 实现 CLI（typer）与 Web UI（FastAPI + 简单前端）
- systemd 单元与运行配置
- 日志与状态页面

## M1 运行切换

- 新 unit 模板：`deploy/systemd/localfile-cloudsync.service`
- 切换脚本：`scripts/switch_m1_service.sh`
- 默认切换命令（不影响旧服务）：`scripts/switch_m1_service.sh prepare`
- 详细说明：`docs/M1_SWITCH.md`
