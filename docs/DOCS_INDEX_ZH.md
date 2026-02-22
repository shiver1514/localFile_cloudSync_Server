# 文档总览（DOCS INDEX）

## 1. 项目入口

- 项目总览与常用命令：`README.md`
- 变更日志：`CHANGELOG.md`
- 飞书 API 映射：`docs/FEISHU_API_MAPPING_ZH.md`

## 2. 运维与发布

- 安装部署与开机自启：`docs/DEPLOYMENT_GUIDE_ZH.md`
- 发布/回滚流程：`docs/RELEASE_PLAYBOOK_ZH.md`
- 发布说明模板：`docs/CHANGELOG_TEMPLATE.md`
- 已发布版本说明：`docs/releases/`
- UI 截图规范：`docs/screenshots/README.md`

## 3. 工程与质量

- 工程化路线与阶段目标：`docs/ENGINEERING_ROADMAP_ZH.md`
- OpenClaw 记忆文档（长期上下文）：`docs/OPENCLAW_AGENT_MEMORY_ZH.md`

## 4. 文档维护规则

- 原则：只保留“当前仍可执行、可维护、可复用”的文档。
- 删除条件：
  - 与当前实现重复且无额外信息价值
  - 仅服务于历史迁移阶段，且对应阶段已完成
  - 模板或草稿长期未使用且有正式文档替代
- 新文档命名建议：
  - 中文策略/流程文档：`*_ZH.md`
  - 发布记录：`docs/releases/vX.Y.Z.md`
