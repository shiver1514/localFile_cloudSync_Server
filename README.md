# localFile_cloudSync_Server

本项目是本地目录与飞书 Drive 的同步服务，包含 CLI、Web 控制台、定时调度与 systemd 用户态运行。

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

## 参考文档

- 文档总览：`docs/DOCS_INDEX_ZH.md`
- OpenClaw 项目记忆：`docs/OPENCLAW_AGENT_MEMORY_ZH.md`
- 工程化路线：`docs/ENGINEERING_ROADMAP_ZH.md`
- 发布手册：`docs/RELEASE_PLAYBOOK_ZH.md`
- 变更模板：`docs/CHANGELOG_TEMPLATE.md`
