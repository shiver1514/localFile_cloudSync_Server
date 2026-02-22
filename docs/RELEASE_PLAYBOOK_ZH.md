# 发布工程化手册（ZH）

## 版本号规范

采用语义化版本（SemVer）：`MAJOR.MINOR.PATCH`。

- `MAJOR`：不兼容变更（API/配置/行为断裂）。
- `MINOR`：向后兼容新增能力。
- `PATCH`：向后兼容修复与小优化。

标签格式统一：`vMAJOR.MINOR.PATCH`，例如 `v0.2.1`。

## 发布前门禁

必须先通过：

```bash
make check
```

且运行态健康检查通过：

```bash
curl -fsS http://127.0.0.1:8765/api/healthz
curl -fsS http://127.0.0.1:8765/api/readyz
```

## 标准发布流程

1. 生成版本与发布文件

```bash
scripts/release.sh --bump patch
```

2. 推送提交和标签

```bash
git push origin <branch>
git push origin --tags
```

3. 在平台发布页附上 `docs/releases/vX.Y.Z.md`。

## 回滚流程

指定目标版本快速回滚（会创建备份分支）：

```bash
scripts/rollback_release.sh --target v0.1.0
```

可选：回滚后自动重启服务

```bash
scripts/rollback_release.sh --target v0.1.0 --restart-service
```

## 注意事项

- 默认要求工作区干净；如需跳过可用 `--allow-dirty`（不推荐）。
- `release.sh` 默认会提交并打标签；可用 `--no-commit` 或 `--no-tag` 关闭。
- 先执行 `--dry-run` 预演，确认版本和产物路径无误后再正式发布。
