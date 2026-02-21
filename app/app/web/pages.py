from __future__ import annotations

import json
from html import escape
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from app.core.config import FIXED_LOCAL_ROOT, LAST_RUN_ONCE_PATH, is_local_root_in_scope, load_config

router = APIRouter()


def _as_text(value) -> str:
    if value is None:
        return "-"
    s = str(value).strip()
    return s if s else "-"


def _translate_error(raw: str) -> str:
    s = _as_text(raw)
    if s in ("-", "None"):
        return "无"
    if "访问被拒绝" in s:
        return s
    if "no_available_token" in s or "no_token" in s:
        return "没有可用令牌，请先配置飞书授权。"
    if "download_failed_status_404" in s:
        return "飞书资源不存在（404）。"
    if "feishu_error" in s:
        return "飞书接口返回错误，请检查应用凭证和权限。"
    if "systemctl_unavailable" in s or "Failed to connect to bus" in s:
        return "systemd 不可用，请确认用户会话与 systemd 用户服务状态。"
    if "systemctl_show_failed" in s:
        return "读取 systemd 服务状态失败。"
    if "允许网段配置无效" in s:
        return "访问控制配置错误，请检查 ALLOWED_NETS。"
    if "timed out" in s or "timeout" in s:
        return "请求超时，请检查网络。"
    return f"系统错误：{s}"


def _render_rows(rows: list[tuple[str, str, str]]) -> str:
    chunks: list[str] = []
    for k, v, cls in rows:
        td_cls = f" class='{escape(cls)}'" if cls else ""
        chunks.append(
            "<tr>"
            f"<th>{escape(_as_text(k))}</th>"
            f"<td{td_cls}>{escape(_as_text(v))}</td>"
            "</tr>"
        )
    return "".join(chunks)


def _load_last_run_summary() -> dict | None:
    if not LAST_RUN_ONCE_PATH.exists():
        return None
    try:
        payload = json.loads(LAST_RUN_ONCE_PATH.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return payload
    except Exception:
        return None
    return None


@router.get("/", response_class=HTMLResponse)
def home():
    cfg = load_config()
    configured_local_root = cfg.sync.local_root
    out_of_scope = not is_local_root_in_scope(configured_local_root)
    token_file_path = Path(cfg.auth.user_token_file).expanduser() if cfg.auth.user_token_file else None
    token_exists = bool(token_file_path and token_file_path.exists())
    summary = _load_last_run_summary()

    if out_of_scope:
        local_root_banner = (
            "<div class='banner warn'>"
            "检测到配置中的 <code>sync.local_root</code> 已偏离允许范围。服务运行时将强制锁定为 "
            f"<code>{escape(FIXED_LOCAL_ROOT)}</code>。"
            "</div>"
        )
    else:
        local_root_banner = (
            "<div class='banner info'>"
            "同步目录范围已锁定："
            f"<code>{escape(FIXED_LOCAL_ROOT)}</code>"
            "</div>"
        )

    feishu_rows = [
        ("飞书应用 ID 已配置", "是" if bool(cfg.auth.app_id) else "否", ""),
        ("飞书应用密钥已配置", "是" if bool(cfg.auth.app_secret) else "否", ""),
        ("用户令牌文件", _as_text(cfg.auth.user_token_file), ""),
        ("令牌文件存在", "是" if token_exists else "否", ""),
        ("远端根目录令牌已配置", "是" if bool(cfg.sync.remote_folder_token) else "否", ""),
        ("检查时间", "加载页面时", ""),
    ]

    if summary:
        run_errors = int(summary.get("errors") or 0)
        fatal_error = summary.get("fatal_error")
        run_rows = [
            ("运行 ID", _as_text(summary.get("run_id")), ""),
            ("本地目录", _as_text(summary.get("local_root")), ""),
            ("上传 / 下载", f"{summary.get('uploaded', 0)} / {summary.get('downloaded', 0)}", ""),
            ("冲突数", _as_text(summary.get("conflicts", 0)), ""),
            ("错误数", _as_text(run_errors), "value-bad" if run_errors > 0 else "value-good"),
            (
                "致命错误",
                _translate_error(fatal_error) if fatal_error else "无",
                "value-bad" if fatal_error else "",
            ),
        ]
    else:
        run_rows = [
            ("状态", "暂无运行记录", ""),
            ("说明", "点击“执行一次同步”后会生成摘要。", ""),
        ]

    page = """
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>本地文件云同步控制台</title>
    <style>
      :root {
        --bg-a: #f8fafc;
        --bg-b: #dbeafe;
        --ink: #10213a;
        --muted: #4b607f;
        --card: #ffffff;
        --line: #d6e0ef;
        --ok: #0f766e;
        --warn: #b45309;
        --bad: #b91c1c;
        --info: #1d4ed8;
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        color: var(--ink);
        font-family: "Noto Sans SC", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
        background:
          radial-gradient(circle at 15% 10%, rgba(56, 189, 248, 0.24), transparent 40%),
          radial-gradient(circle at 85% 20%, rgba(251, 191, 36, 0.2), transparent 42%),
          linear-gradient(135deg, var(--bg-a), var(--bg-b));
      }
      .container {
        max-width: 1180px;
        margin: 0 auto;
        padding: 24px 16px 40px;
      }
      h1 {
        margin: 0 0 6px;
        font-size: 28px;
        letter-spacing: 0.5px;
      }
      .subtitle {
        margin: 0 0 18px;
        color: var(--muted);
      }
      .banner {
        border-radius: 12px;
        padding: 12px 14px;
        margin: 0 0 16px;
        font-size: 14px;
      }
      .banner code {
        font-family: "JetBrains Mono", "Fira Code", "SFMono-Regular", Consolas, monospace;
      }
      .banner.info {
        border: 1px solid #bfdbfe;
        background: #eff6ff;
        color: #1e3a8a;
      }
      .banner.warn {
        border: 1px solid #fdba74;
        background: #fff7ed;
        color: #9a3412;
      }
      .grid {
        display: grid;
        gap: 14px;
        margin-bottom: 14px;
      }
      .grid.two {
        grid-template-columns: 1fr 1fr;
      }
      .card {
        background: var(--card);
        border: 1px solid var(--line);
        border-radius: 16px;
        padding: 14px;
        box-shadow: 0 8px 24px rgba(2, 6, 23, 0.06);
        animation: fadeIn 0.32s ease;
      }
      .card h2 {
        margin: 0 0 10px;
        font-size: 17px;
      }
      .muted {
        color: var(--muted);
      }
      table.kv {
        width: 100%;
        border-collapse: collapse;
        font-size: 14px;
      }
      table.kv th,
      table.kv td {
        text-align: left;
        border-bottom: 1px solid #edf2f7;
        padding: 8px 10px;
        vertical-align: top;
      }
      table.kv th {
        width: 40%;
        color: #334155;
      }
      table.kv td {
        white-space: pre-wrap;
        word-break: break-word;
      }
      .value-good {
        color: var(--ok);
        font-weight: 600;
      }
      .value-bad {
        color: var(--bad);
        font-weight: 600;
      }
      .actions {
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
      }
      button {
        border: 0;
        border-radius: 10px;
        background: #0f766e;
        color: #fff;
        padding: 10px 12px;
        font-size: 14px;
        cursor: pointer;
      }
      button.secondary {
        background: #1d4ed8;
      }
      button.warn {
        background: #b45309;
      }
      button:disabled {
        opacity: 0.65;
        cursor: not-allowed;
      }
      .status-wrap {
        display: flex;
        align-items: center;
        gap: 10px;
        margin-bottom: 8px;
      }
      .badge {
        display: inline-block;
        border-radius: 999px;
        padding: 4px 10px;
        font-size: 12px;
        font-weight: 700;
      }
      .badge.idle {
        background: #e2e8f0;
        color: #334155;
      }
      .badge.running {
        background: #ffedd5;
        color: #9a3412;
        animation: pulse 1s infinite ease-in-out;
      }
      .badge.success {
        background: #dcfce7;
        color: #166534;
      }
      .badge.failed {
        background: #fee2e2;
        color: #991b1b;
      }
      .alert {
        border-radius: 10px;
        padding: 10px 12px;
        margin-top: 10px;
        font-size: 14px;
      }
      .alert.success {
        border: 1px solid #86efac;
        background: #f0fdf4;
        color: #166534;
      }
      .alert.warn {
        border: 1px solid #fdba74;
        background: #fff7ed;
        color: #9a3412;
      }
      .alert.danger {
        border: 1px solid #fca5a5;
        background: #fef2f2;
        color: #991b1b;
      }
      .hidden {
        display: none;
      }
      .log {
        margin: 0;
        background: #0f172a;
        color: #e2e8f0;
        border-radius: 10px;
        padding: 10px;
        max-height: 260px;
        overflow: auto;
        white-space: pre-wrap;
        word-break: break-word;
      }
      .cfg-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 10px;
      }
      .cfg-grid label {
        display: block;
        font-size: 13px;
      }
      .cfg-grid input {
        width: 100%;
        margin-top: 4px;
        border: 1px solid #cbd5e1;
        border-radius: 8px;
        padding: 8px;
      }
      .cfg-grid .full {
        grid-column: 1 / -1;
      }
      .message {
        margin-top: 10px;
      }
      .message.info { color: var(--info); }
      .message.success { color: #166534; }
      .message.warn { color: #9a3412; }
      .message.danger { color: #991b1b; }
      @media (max-width: 900px) {
        .grid.two,
        .cfg-grid {
          grid-template-columns: 1fr;
        }
      }
      @keyframes fadeIn {
        from { transform: translateY(4px); opacity: 0; }
        to { transform: translateY(0); opacity: 1; }
      }
      @keyframes pulse {
        0% { opacity: 0.8; }
        50% { opacity: 1; }
        100% { opacity: 0.8; }
      }
    </style>
  </head>
  <body>
    <div class="container">
      <h1>本地文件云同步控制台</h1>
      <p class="subtitle">服务名：<code>localfile-cloudsync.service</code></p>
      __LOCAL_ROOT_BANNER__

      <section class="grid two">
        <article class="card">
          <h2>服务概览</h2>
          <table class="kv"><tbody>
            <tr><th>固定同步目录</th><td><code>__FIXED_LOCAL_ROOT__</code></td></tr>
            <tr><th>配置中的 local_root</th><td><code>__CONFIGURED_LOCAL_ROOT__</code></td></tr>
            <tr><th>Web 地址</th><td><code>http://__WEB_BIND_HOST__:__WEB_PORT__</code></td></tr>
            <tr><th>日志文件</th><td><code>__LOG_PATH__</code></td></tr>
            <tr><th>数据库文件</th><td><code>__DB_PATH__</code></td></tr>
            <tr><th>最近运行摘要文件</th><td><code>__LAST_RUN_PATH__</code></td></tr>
          </tbody></table>
        </article>
        <article class="card">
          <h2>快捷操作</h2>
          <div class="actions">
            <button id="btnRunOnce" onclick="runOnce()">执行一次同步</button>
            <button class="secondary" onclick="refreshAll()">刷新全部</button>
            <button class="secondary" onclick="refreshFeishu()">刷新飞书状态</button>
            <button class="secondary" onclick="refreshRunOnce()">刷新运行摘要</button>
            <button class="secondary" onclick="refreshServiceStatus()">刷新服务状态</button>
            <button class="secondary" onclick="refreshLogs()">刷新日志</button>
            <button class="warn" onclick="restartService()">重启服务</button>
          </div>
          <p id="actionMessage" class="message info">准备就绪。</p>
        </article>
      </section>

      <section class="grid two">
        <article class="card">
          <h2>飞书状态</h2>
          <table id="feishuTable" class="kv"><tbody>__FEISHU_ROWS__</tbody></table>
        </article>
        <article class="card">
          <h2>systemd 服务状态</h2>
          <table id="serviceTable" class="kv"><tbody>
            <tr><th>状态</th><td>待刷新</td></tr>
          </tbody></table>
          <details>
            <summary>systemctl 输出（最近 8 行）</summary>
            <pre id="serviceStatusText" class="log"></pre>
          </details>
        </article>
      </section>

      <section class="card">
        <h2>单次同步执行状态</h2>
        <div class="status-wrap">
          <span id="runStateBadge" class="badge idle">空闲</span>
          <span id="runStateText" class="muted">尚未执行本轮同步。</span>
        </div>
        <div id="runAlert" class="alert hidden"></div>
      </section>

      <section class="card">
        <h2>最近一次运行摘要</h2>
        <table id="runSummaryTable" class="kv"><tbody>__RUN_ROWS__</tbody></table>
      </section>

      <section class="grid two">
        <article class="card">
          <h2>日志（最近 200 行）</h2>
          <pre id="logs" class="log"></pre>
        </article>
        <article class="card">
          <h2>数据库概览</h2>
          <pre id="db" class="log"></pre>
        </article>
      </section>

      <section class="card">
        <h2>配置（快速编辑）</h2>
        <form id="cfg" class="cfg-grid">
          <label>监听地址（web_bind_host）
            <input name="web_bind_host" value="__WEB_BIND_HOST__" />
          </label>
          <label>端口（web_port）
            <input name="web_port" value="__WEB_PORT__" />
          </label>
          <label class="full">同步目录（sync.local_root，可填写但会被锁定）
            <input name="sync.local_root" value="__CONFIGURED_LOCAL_ROOT__" />
          </label>
          <label>飞书应用 ID（auth.app_id）
            <input name="auth.app_id" value="__AUTH_APP_ID__" />
          </label>
          <label>飞书应用密钥（auth.app_secret）
            <input name="auth.app_secret" value="__AUTH_APP_SECRET__" />
          </label>
          <label class="full">用户令牌文件（auth.user_token_file）
            <input name="auth.user_token_file" value="__AUTH_USER_TOKEN_FILE__" />
          </label>
          <div class="full">
            <button type="button" onclick="saveCfg()">保存配置</button>
            <p class="muted">说明：`sync.local_root` 运行时固定为 <code>__FIXED_LOCAL_ROOT__</code>。</p>
          </div>
        </form>
      </section>
    </div>

    <script>
      const FIXED_LOCAL_ROOT = "__FIXED_LOCAL_ROOT__";
      const INITIAL_LOCAL_ROOT_OUT_OF_SCOPE = __OUT_OF_SCOPE__;

      function escapeHtml(value) {
        return String(value)
          .replace(/&/g, "&amp;")
          .replace(/</g, "&lt;")
          .replace(/>/g, "&gt;");
      }

      function asText(value, fallback) {
        if (value === null || value === undefined) return fallback || "-";
        const s = String(value).trim();
        return s ? s : (fallback || "-");
      }

      function asYesNo(value) {
        if (value === null || value === undefined) return "未知";
        return value ? "是" : "否";
      }

      function localTime(value) {
        if (!value) return "-";
        try {
          return new Date(value).toLocaleString("zh-CN", { hour12: false });
        } catch (_err) {
          return String(value);
        }
      }

      function translateError(raw) {
        const s = asText(raw, "");
        if (!s) return "无";
        if (s.indexOf("访问被拒绝") >= 0) {
          return s;
        }
        if (s.indexOf("access denied") >= 0 || s.indexOf("forbidden") >= 0) {
          return "访问被拒绝，请确认访问网段配置。";
        }
        if (s.indexOf("no_available_token") >= 0 || s.indexOf("no_token") >= 0) {
          return "没有可用令牌，请先配置飞书授权。";
        }
        if (s.indexOf("download_failed_status_404") >= 0) {
          return "飞书资源不存在（404）。";
        }
        if (s.indexOf("feishu_error") >= 0) {
          return "飞书接口返回错误，请检查应用凭证和权限。";
        }
        if (s.indexOf("systemctl_unavailable") >= 0 || s.indexOf("Failed to connect to bus") >= 0) {
          return "systemd 不可用，请确认当前会话具备 systemd 用户服务能力。";
        }
        if (s.indexOf("systemctl_show_failed") >= 0) {
          return "读取 systemd 服务状态失败。";
        }
        if (s.indexOf("允许网段配置无效") >= 0) {
          return "访问控制配置错误，请检查 ALLOWED_NETS。";
        }
        if (s.indexOf("Failed to fetch") >= 0) {
          return "请求失败，请检查服务是否启动以及网络是否可达。";
        }
        if (s.indexOf("timed out") >= 0 || s.indexOf("timeout") >= 0) {
          return "请求超时，请检查网络。";
        }
        return "系统错误：" + s;
      }

      function formatSystemdState(raw, mapping) {
        const key = asText(raw, "-");
        if (key === "-") return "-";
        const label = mapping[key];
        return label ? (label + "（" + key + "）") : key;
      }

      function formatLoadState(value) {
        return formatSystemdState(value, {
          loaded: "已加载",
          not_found: "未找到",
          masked: "已屏蔽",
          error: "错误"
        });
      }

      function formatActiveState(value) {
        return formatSystemdState(value, {
          active: "运行中",
          inactive: "未运行",
          failed: "失败",
          activating: "启动中",
          deactivating: "停止中",
          reloading: "重载中"
        });
      }

      function formatSubState(value) {
        return formatSystemdState(value, {
          running: "运行中",
          exited: "已退出",
          dead: "已停止",
          auto_restart: "自动重启",
          start_pre: "启动前检查",
          start: "启动中",
          stop: "停止中"
        });
      }

      function formatUnitFileState(value) {
        return formatSystemdState(value, {
          enabled: "已启用",
          disabled: "已禁用",
          static: "静态",
          masked: "已屏蔽",
          linked: "已链接"
        });
      }

      function setActionMessage(message, level) {
        const node = document.getElementById("actionMessage");
        node.textContent = message;
        node.className = "message " + (level || "info");
      }

      function setRunState(state, text) {
        const badge = document.getElementById("runStateBadge");
        const stateText = document.getElementById("runStateText");
        badge.className = "badge " + state;
        if (state === "running") badge.textContent = "执行中";
        else if (state === "success") badge.textContent = "成功";
        else if (state === "failed") badge.textContent = "失败";
        else badge.textContent = "空闲";
        stateText.textContent = text || "";
      }

      function setRunAlert(level, message) {
        const node = document.getElementById("runAlert");
        if (!message) {
          node.className = "alert hidden";
          node.textContent = "";
          return;
        }
        node.className = "alert " + (level || "warn");
        node.textContent = message;
      }

      function renderRows(tableId, rows) {
        const tbody = document.querySelector("#" + tableId + " tbody");
        tbody.innerHTML = rows.map(function (row) {
          const cls = row[2] ? (" class='" + escapeHtml(row[2]) + "'") : "";
          return "<tr><th>" + escapeHtml(asText(row[0])) + "</th><td" + cls + ">" + escapeHtml(asText(row[1])) + "</td></tr>";
        }).join("");
      }

      async function requestJson(method, url, payload) {
        const options = { method: method || "GET", headers: {} };
        if (payload !== undefined) {
          options.headers["Content-Type"] = "application/json";
          options.body = JSON.stringify(payload);
        }

        const resp = await fetch(url, options);
        const raw = await resp.text();
        let data = {};
        if (raw) {
          try { data = JSON.parse(raw); }
          catch (_e) { data = { raw: raw }; }
        }
        if (!resp.ok) {
          const detail = data.detail || data.error || data.raw || ("HTTP 状态 " + resp.status);
          throw new Error(detail);
        }
        return data;
      }

      function applyRunSummary(summary, fromRunAction) {
        if (!summary) {
          renderRows("runSummaryTable", [
            ["状态", "暂无运行记录", ""],
            ["说明", "点击“执行一次同步”后会生成摘要。", ""]
          ]);
          if (!fromRunAction) setRunState("idle", "尚未执行本轮同步。");
          return;
        }

        const errors = Number(summary.errors || 0);
        const fatalError = summary.fatal_error;
        const hasFailure = Boolean(fatalError) || errors > 0;
        const rows = [
          ["运行 ID", asText(summary.run_id), ""],
          ["开始目录", asText(summary.local_root), ""],
          ["远端根目录令牌", asText(summary.remote_root_token), ""],
          ["本地文件数", asText(summary.local_total, "0"), ""],
          ["远端文件数", asText(summary.remote_total, "0"), ""],
          ["上传 / 下载", asText(summary.uploaded, "0") + " / " + asText(summary.downloaded, "0"), ""],
          ["冲突", asText(summary.conflicts, "0"), Number(summary.conflicts || 0) > 0 ? "value-bad" : ""],
          ["错误数", asText(errors, "0"), errors > 0 ? "value-bad" : "value-good"],
          ["致命错误", fatalError ? translateError(fatalError) : "无", fatalError ? "value-bad" : ""]
        ];

        if (summary.scope_warning) {
          rows.push([
            "范围警告",
            "配置中的 local_root 已被锁定为 " + asText(summary.scope_warning.applied_local_root, FIXED_LOCAL_ROOT),
            "value-bad"
          ]);
        }
        renderRows("runSummaryTable", rows);

        if (hasFailure) {
          setRunState("failed", "本次执行失败，请查看错误详情。");
          const details = fatalError ? translateError(fatalError) : ("错误数：" + errors);
          setRunAlert("danger", details);
        } else {
          setRunState("success", "本次执行成功。");
          if (fromRunAction) setRunAlert("success", "同步已完成，未发现致命错误。");
        }
      }

      async function refreshFeishu() {
        try {
          const data = await requestJson("GET", "/api/status/feishu");
          const error = data.token && data.token.error ? data.token.error : (data.connectivity ? data.connectivity.error : "");
          const rows = [
            ["检查时间", localTime(data.checked_at), ""],
            ["配置完整（app_id）", asYesNo(data.config && data.config.app_id_configured), ""],
            ["配置完整（app_secret）", asYesNo(data.config && data.config.app_secret_configured), ""],
            ["用户令牌文件", asText(data.config ? data.config.user_token_file : "-"), ""],
            ["令牌文件存在", asYesNo(data.config && data.config.user_token_file_exists), ""],
            ["可用令牌", asYesNo(data.token && data.token.available), (data.token && data.token.available) ? "value-good" : "value-bad"],
            ["令牌类型", asText(data.token ? data.token.type : "-"), ""],
            ["API 连通", asYesNo(data.connectivity && data.connectivity.api_access), (data.connectivity && data.connectivity.api_access) ? "value-good" : "value-bad"],
            ["远端根目录令牌", asText(data.connectivity ? data.connectivity.root_folder_token : "-"), ""],
            ["错误信息", error ? translateError(error) : "无", error ? "value-bad" : ""]
          ];
          renderRows("feishuTable", rows);
        } catch (err) {
          renderRows("feishuTable", [
            ["状态", "读取失败", "value-bad"],
            ["错误", translateError(err.message), "value-bad"]
          ]);
          setActionMessage("刷新飞书状态失败：" + translateError(err.message), "danger");
        }
      }

      async function refreshServiceStatus() {
        try {
          const data = await requestJson("GET", "/api/status/service");
          const activeState = asText(data.active_state, "-");
          const rows = [
            ["检查时间", localTime(data.checked_at), ""],
            ["systemd 可用", asYesNo(data.systemd_available), data.systemd_available ? "value-good" : "value-bad"],
            ["加载状态（LoadState）", formatLoadState(data.load_state), ""],
            ["运行状态（ActiveState）", formatActiveState(activeState), activeState === "active" ? "value-good" : "value-bad"],
            ["子状态（SubState）", formatSubState(data.sub_state), ""],
            ["开机状态（UnitFileState）", formatUnitFileState(data.unit_file_state), ""],
            ["主进程 ID（MainPID）", asText(data.main_pid), ""],
            ["错误信息", data.error ? translateError(data.error) : "无", data.error ? "value-bad" : ""]
          ];
          renderRows("serviceTable", rows);
          document.getElementById("serviceStatusText").textContent = asText(data.status_text, "");
        } catch (err) {
          renderRows("serviceTable", [
            ["状态", "读取失败", "value-bad"],
            ["错误", translateError(err.message), "value-bad"]
          ]);
          document.getElementById("serviceStatusText").textContent = "";
          setActionMessage("刷新服务状态失败：" + translateError(err.message), "danger");
        }
      }

      async function refreshRunOnce() {
        try {
          const data = await requestJson("GET", "/api/status/run-once");
          applyRunSummary(data.summary || null, false);
          if (data.error) {
            setRunAlert("warn", "读取摘要时出现错误：" + translateError(data.error));
          }
        } catch (err) {
          applyRunSummary(null, false);
          setRunAlert("warn", "读取摘要失败：" + translateError(err.message));
        }
      }

      async function refreshLogs() {
        try {
          const data = await requestJson("GET", "/api/logs?n=200");
          document.getElementById("logs").textContent = asText(data.tail, "");
        } catch (err) {
          document.getElementById("logs").textContent = "读取日志失败：" + translateError(err.message);
        }
      }

      async function refreshDb() {
        try {
          const data = await requestJson("GET", "/api/db");
          document.getElementById("db").textContent = JSON.stringify(data, null, 2);
        } catch (err) {
          document.getElementById("db").textContent = "读取数据库状态失败：" + translateError(err.message);
        }
      }

      async function restartService() {
        try {
          await requestJson("POST", "/api/actions/restart", {});
          setActionMessage("服务重启命令已发送。", "success");
          await refreshServiceStatus();
        } catch (err) {
          setActionMessage("重启服务失败：" + translateError(err.message), "danger");
        }
      }

      async function runOnce() {
        const btn = document.getElementById("btnRunOnce");
        btn.disabled = true;
        btn.textContent = "执行中...";
        setRunState("running", "正在执行同步，请稍候...");
        setRunAlert("", "");
        try {
          const data = await requestJson("POST", "/api/actions/run-once", {});
          applyRunSummary(data, true);
          if (data.fatal_error || Number(data.errors || 0) > 0) {
            setActionMessage("同步执行完成，但出现错误。", "warn");
          } else {
            setActionMessage("同步执行成功。", "success");
          }
          if (data.scope_warning) {
            setRunAlert("warn", "检测到 local_root 配置越界，已按固定范围执行。");
          }
          await refreshFeishu();
          await refreshServiceStatus();
          await refreshLogs();
          await refreshDb();
        } catch (err) {
          const message = translateError(err.message);
          setRunState("failed", "执行失败。");
          setRunAlert("danger", message);
          setActionMessage("执行同步失败：" + message, "danger");
        } finally {
          btn.disabled = false;
          btn.textContent = "执行一次同步";
        }
      }

      async function saveCfg() {
        const form = document.getElementById("cfg");
        const payload = {
          web_bind_host: form["web_bind_host"].value,
          web_port: parseInt(form["web_port"].value, 10),
          sync: { local_root: form["sync.local_root"].value },
          auth: {
            app_id: form["auth.app_id"].value,
            app_secret: form["auth.app_secret"].value,
            user_token_file: form["auth.user_token_file"].value
          }
        };
        try {
          const result = await requestJson("POST", "/api/config", payload);
          if (result.warnings && result.warnings.length > 0) {
            setActionMessage("配置已保存。local_root 已被锁定到固定目录。", "warn");
            setRunAlert("warn", "配置中的 local_root 不在允许范围，系统已自动锁定为固定目录。");
          } else {
            setActionMessage("配置已保存。", "success");
          }
        } catch (err) {
          setActionMessage("保存配置失败：" + translateError(err.message), "danger");
        }
      }

      async function refreshAll() {
        await refreshFeishu();
        await refreshRunOnce();
        await refreshServiceStatus();
        await refreshLogs();
        await refreshDb();
      }

      if (INITIAL_LOCAL_ROOT_OUT_OF_SCOPE) {
        setRunAlert("warn", "检测到配置中的 local_root 越界，运行时会强制锁定为固定目录。");
      }
      refreshAll();
    </script>
  </body>
</html>
"""

    return (
        page.replace("__LOCAL_ROOT_BANNER__", local_root_banner)
        .replace("__FIXED_LOCAL_ROOT__", escape(FIXED_LOCAL_ROOT))
        .replace("__CONFIGURED_LOCAL_ROOT__", escape(_as_text(configured_local_root)))
        .replace("__WEB_BIND_HOST__", escape(_as_text(cfg.web_bind_host)))
        .replace("__WEB_PORT__", escape(_as_text(cfg.web_port)))
        .replace("__LOG_PATH__", escape(_as_text(cfg.logging.file)))
        .replace("__DB_PATH__", escape(_as_text(cfg.database.path)))
        .replace("__LAST_RUN_PATH__", escape(str(LAST_RUN_ONCE_PATH)))
        .replace("__AUTH_APP_ID__", escape(_as_text(cfg.auth.app_id)))
        .replace("__AUTH_APP_SECRET__", escape(_as_text(cfg.auth.app_secret)))
        .replace("__AUTH_USER_TOKEN_FILE__", escape(_as_text(cfg.auth.user_token_file)))
        .replace("__OUT_OF_SCOPE__", "true" if out_of_scope else "false")
        .replace("__FEISHU_ROWS__", _render_rows(feishu_rows))
        .replace("__RUN_ROWS__", _render_rows(run_rows))
    )
