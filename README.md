# localFile_cloudSync_Server

本项目是本地目录与飞书 Drive 的同步服务，包含 CLI、Web 控制台、定时调度与 systemd 用户态运行。

## 使用背景

为了实现“本地空间 <-> 飞书云空间”的稳定同步，项目采用以下协作边界：

- OpenClaw 主要操作本地工作空间（文档整理、结构调整、内容生成）。
- 用户主要在飞书云空间操作（协作、分享、在线编辑）。
- 同步服务负责两侧状态对齐，保证最终一致性。
- OpenClaw 不直接操作飞书 OpenAPI，由同步服务统一代理与调度。

这样做的目标：

- 减少不必要的云 API 调用与 token 消耗。
- 将云端鉴权、重试、冲突处理集中到一个服务层，提升稳定性。
- 提高自动化效率：OpenClaw 只关心本地文件任务，云端同步由服务后台完成。

## 目录说明

- 当前实现：`app/`
- 服务单元模板：`deploy/systemd/localfile-cloudsync.service`
- 运维脚本：`scripts/`
- 文档入口：`docs/DOCS_INDEX_ZH.md`

## 快速启动

```bash
cd /home/n150/openclaw_workspace/localFile_cloudSync_Server
source venv/bin/activate
cd app
python -m localfilesync.cli.main --help
python -m localfilesync.web.main
```

## 使用环境与依赖

推荐环境：

- OS：Linux（已针对 `systemd --user` 运维方式适配）
- Python：`3.12+`
- Git：`2.43+`（用于发布与版本管理）

核心运行依赖（见 `app/pyproject.toml`）：

- `fastapi`
- `uvicorn`
- `pydantic`
- `pyyaml`
- `requests`
- `typer`
- `rich`

开发依赖：

- `ruff`
- `mypy`
- `pytest`
- `pytest-cov`

安装开发依赖：

```bash
make install
```

## 云空间支持范围（当前版本）

当前仅支持飞书云空间，且仅支持**飞书用户身份链路**：

- `user_access`（即 `user_access_token`）OAuth 授权方案

当前不支持：

- 其他云空间（例如钉钉）
- 非用户身份链路作为主同步模式

## 工程化命令

在仓库根目录执行：

```bash
make install      # 安装开发依赖
make lint         # ruff 检查
make typecheck    # mypy 检查
make test         # pytest
make check        # lint + typecheck + test + compile
make release      # 查看发布脚本用法
make rollback     # 查看回滚脚本用法
```

## 健康检查接口

- `GET /api/healthz`：进程存活检查（liveness）
- `GET /api/readyz`：服务就绪检查（readiness，失败返回 503）

## 界面截图

截图目录：`docs/screenshots/`

- 建议文件名：
  - `dashboard-overview.png`：控制台总览
  - `config-panel.png`：配置区（鉴权与基础配置）
  - `drive-tree.png`：Drive 文件树
  - `runtime-status.png`：运行状态与自动同步
  - `logs-panel.png`：日志巡检区

截图说明模板：`docs/screenshots/README.md`

## 参考文档

- 文档总览：`docs/DOCS_INDEX_ZH.md`
- OpenClaw 项目记忆：`docs/OPENCLAW_AGENT_MEMORY_ZH.md`
- 工程化路线：`docs/ENGINEERING_ROADMAP_ZH.md`
- 发布手册：`docs/RELEASE_PLAYBOOK_ZH.md`
- 变更模板：`docs/CHANGELOG_TEMPLATE.md`
