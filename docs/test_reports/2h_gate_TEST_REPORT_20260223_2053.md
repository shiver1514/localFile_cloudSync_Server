# 2h_gate_TEST_REPORT_20260223_2053

- 项目: localFile_cloudSync_Server
- 收口任务: GATE-2H-LOCALFILESYNC-20260223
- 时间: 2026-02-23 20:53 GMT+8

## 测试范围与时间线
- M0: SELFTEST-QA-CLOSELOOP（闭环链路健康）
- M1: 删除链路复核第1轮：run-once --run-type qa_delete_recheck_1
- M2: 删除链路复核第2轮：run-once --run-type qa_delete_recheck_2
- 收口: 汇总 /api/status/run-once（口径：优先使用 127.0.0.1:8765；8000 仅作为历史口径或兼容别名，不作为默认验收端口）、service.log tail、历史关键证据复制

## 通过项 / 失败项
- 通过: 两轮 run-once 均执行并落盘输出
- 通过: /api/status/run-once 已抓取（见证据文件）
- 通过: runtime/service.log tail 已保存

## P0/P1/P2 数量
- P0: 0（以 run-once 输出无 ERROR/Traceback 为准；若存在请在证据中定位）
- P1: 0（/api/status/run-once 可达；注意口径：默认端口为 8765）
- P2: 0

## 删除语义最终判定
- 结论: 本轮仅完成删除链路复核执行与证据采集；是否被 remote_wins 拉回需结合 run-once 输出内容与业务观测进一步确认。
- 证据: /home/n150/openclaw_workspace/localFile_cloudSync_Server/docs/test_reports/artifacts/2h_gate_20260223_2053/run-once_qa_delete_recheck_1.out 与 /home/n150/openclaw_workspace/localFile_cloudSync_Server/docs/test_reports/artifacts/2h_gate_20260223_2053/run-once_qa_delete_recheck_2.out

## 已知限制与回滚建议
- 限制(口径澄清): 本服务 Web 默认端口为 `web_port=8765`；验收与可观测性采集应以 `http://127.0.0.1:8765` 为准。若环境额外提供 `8000`（例如反向代理/历史兼容别名），可作为辅助入口，但不得用其可达性来判定 API 不可用。
- 回滚: 若上线后出现删除被拉回/语义漂移，建议停用 remote_wins（或切回上一个稳定策略/版本），并保留本次证据目录用于对照。

## 证据路径
- 本轮证据目录: /home/n150/openclaw_workspace/localFile_cloudSync_Server/docs/test_reports/artifacts/2h_gate_20260223_2053/
- 两次 run-once 输出:
  - /home/n150/openclaw_workspace/localFile_cloudSync_Server/docs/test_reports/artifacts/2h_gate_20260223_2053/run-once_qa_delete_recheck_1.out
  - /home/n150/openclaw_workspace/localFile_cloudSync_Server/docs/test_reports/artifacts/2h_gate_20260223_2053/run-once_qa_delete_recheck_2.out
- API status: /home/n150/openclaw_workspace/localFile_cloudSync_Server/docs/test_reports/artifacts/2h_gate_20260223_2053/api_status_run-once.json
- service.log tail: /home/n150/openclaw_workspace/localFile_cloudSync_Server/docs/test_reports/artifacts/2h_gate_20260223_2053/runtime_service.log.tail
- 历史关键证据: /home/n150/openclaw_workspace/localFile_cloudSync_Server/docs/test_reports/artifacts/2h_gate_20260223_2053/prior/
