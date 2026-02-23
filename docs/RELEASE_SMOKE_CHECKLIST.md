# Release Smoke Checklist

适用范围：发布后 5 分钟内的最小可用性检查（值班/测试/用户可直接照抄执行）。

目标：确认端口口径（8765）+ API 可达 + CLI 可用（不跑全量同步）。

> 口径：**产品仅支持 Web 端口 8765**。回归/值班不得使用 8000 作为验收标准。

---

## 1) 确认服务端口与进程

```bash
systemctl --user restart localfile-cloudsync.service
systemctl --user status localfile-cloudsync.service --no-pager
ss -lntp | egrep '(:8765|:8000)'
```

通过标准：`8765` LISTEN；不要求 `8000`。

---

## 2) API 冒烟（只认 8765）

```bash
curl -fsS http://127.0.0.1:8765/api/healthz && echo
curl -fsS http://127.0.0.1:8765/api/status/run-once | head
curl -fsS http://127.0.0.1:8765/api/status/service | head
```

通过标准：三条都返回 `200` 且为 JSON。

---

## 3) CLI 冒烟（优先 dry-run）

```bash
./venv/bin/localfilesync-cli status | head -n 60
./venv/bin/localfilesync-cli run-once --dry-run
```

通过标准：
- 无异常栈（traceback）
- `status` 中能看到 `web=http://127.0.0.1:8765`
- `run-once --dry-run` exit code 为 0

---

## 4) 失败时快速取证（给开发）

```bash
journalctl --user -u localfile-cloudsync.service -n 200 --no-pager
tail -n 200 runtime/service.log
```

回传最小信息：失败命令 + 返回码 + 上述两段日志输出（注意脱敏 token）。
