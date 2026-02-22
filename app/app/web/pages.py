from __future__ import annotations

from html import escape

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from app.core.config import FIXED_LOCAL_ROOT, LAST_RUN_ONCE_PATH, is_local_root_in_scope, load_config

router = APIRouter()


def _as_text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


@router.get("/", response_class=HTMLResponse)
def home():
    cfg = load_config()
    out_of_scope = not is_local_root_in_scope(cfg.sync.local_root)

    if out_of_scope:
        scope_banner = (
            "<div class='banner warn'>"
            "检测到 <code>sync.local_root</code> 不在允许范围，运行时将锁定为 "
            f"<code>{escape(FIXED_LOCAL_ROOT)}</code>"
            "</div>"
        )
    else:
        scope_banner = (
            "<div class='banner info'>"
            "本地同步目录策略：固定锁定 <code>"
            f"{escape(FIXED_LOCAL_ROOT)}"
            "</code>"
            "</div>"
        )

    page = """
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Drive 文件型同步控制台</title>
    <style>
      :root {
        --bg-a: #f5f9ff;
        --bg-b: #e8f3ff;
        --ink: #0a1f3d;
        --muted: #4d6486;
        --line: #d3e2f3;
        --card: #ffffff;
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
          radial-gradient(circle at 10% 12%, rgba(59, 130, 246, 0.15), transparent 40%),
          radial-gradient(circle at 88% 8%, rgba(245, 158, 11, 0.15), transparent 40%),
          linear-gradient(140deg, var(--bg-a), var(--bg-b));
      }
      .app {
        max-width: 1240px;
        margin: 0 auto;
        padding: 20px 16px 36px;
      }
      .header {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        gap: 12px;
      }
      h1 {
        margin: 0;
        font-size: 30px;
        letter-spacing: 0.3px;
      }
      .subtitle {
        margin: 6px 0 0;
        color: var(--muted);
        font-size: 14px;
      }
      .header-actions {
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
      }
      .banner {
        border-radius: 12px;
        padding: 10px 12px;
        margin-top: 12px;
        margin-bottom: 10px;
        font-size: 14px;
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
      .global-msg {
        min-height: 20px;
        font-size: 14px;
        margin-bottom: 10px;
      }
      .global-msg.info { color: var(--info); }
      .global-msg.success { color: #166534; }
      .global-msg.warn { color: var(--warn); }
      .global-msg.danger { color: var(--bad); }
      .stats-grid {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 10px;
        margin-bottom: 12px;
      }
      .stat-card {
        background: #ffffff;
        border: 1px solid #d9e6f7;
        border-radius: 12px;
        padding: 10px 12px;
      }
      .stat-label {
        font-size: 12px;
        color: var(--muted);
      }
      .stat-value {
        margin-top: 3px;
        font-size: 15px;
        font-weight: 700;
      }
      .stat-value-wrap {
        margin-top: 3px;
        display: inline-flex;
        align-items: center;
        gap: 8px;
      }
      .stat-value.good { color: #166534; }
      .stat-value.warn { color: #b45309; }
      .stat-value.bad { color: #b91c1c; }
      .stat-value.info { color: #1d4ed8; }
      .action-state {
        font-size: 13px;
        color: var(--muted);
        min-height: 18px;
      }
      .action-state.loading { color: #1d4ed8; }
      .action-state.success { color: #166534; }
      .action-state.warn { color: #b45309; }
      .action-state.danger { color: #b91c1c; }
      .tabs {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        margin-bottom: 12px;
      }
      .tab {
        border: 1px solid #bfd3ee;
        background: #f3f8ff;
        color: #1f3b64;
        border-radius: 999px;
        padding: 7px 14px;
        font-size: 14px;
        cursor: pointer;
      }
      .tab.active {
        border-color: #1d4ed8;
        background: #1d4ed8;
        color: #fff;
      }
      .panel {
        display: none;
      }
      .panel.active {
        display: block;
      }
      .grid {
        display: grid;
        gap: 14px;
      }
      .grid.two {
        grid-template-columns: 1fr 1fr;
      }
      .card {
        background: var(--card);
        border: 1px solid var(--line);
        border-radius: 16px;
        padding: 14px;
        box-shadow: 0 8px 20px rgba(15, 23, 42, 0.06);
      }
      .card h2 {
        margin: 0 0 10px;
        font-size: 19px;
      }
      .card h3 {
        margin: 12px 0 8px;
        font-size: 15px;
      }
      .muted { color: var(--muted); }
      .small { font-size: 13px; }
      .hint {
        margin-top: 4px;
        color: var(--muted);
        font-size: 12px;
      }
      code {
        font-family: "JetBrains Mono", "Fira Code", "SFMono-Regular", Consolas, monospace;
      }
      .flow {
        margin: 0 0 10px;
        padding-left: 18px;
        color: #2b4a71;
        font-size: 13px;
      }
      .flow li { margin-bottom: 4px; }
      .form-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 10px;
      }
      .full { grid-column: 1 / -1; }
      label {
        display: block;
        font-size: 13px;
      }
      input, select, textarea {
        width: 100%;
        margin-top: 4px;
        border: 1px solid #c8d8ed;
        border-radius: 10px;
        background: #fff;
        padding: 8px;
        font-size: 14px;
      }
      textarea {
        min-height: 78px;
        resize: vertical;
      }
      .actions {
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
      }
      button {
        border: 0;
        border-radius: 10px;
        background: #0f766e;
        color: #fff;
        padding: 9px 12px;
        font-size: 14px;
        cursor: pointer;
      }
      button.secondary { background: #1d4ed8; }
      button.warn { background: #b45309; }
      button:disabled { opacity: 0.65; cursor: not-allowed; }
      button.btn-loading {
        position: relative;
        padding-left: 34px;
      }
      button.btn-loading::before {
        content: "";
        position: absolute;
        left: 12px;
        top: 50%;
        width: 12px;
        height: 12px;
        margin-top: -6px;
        border: 2px solid rgba(255, 255, 255, 0.75);
        border-top-color: transparent;
        border-radius: 50%;
        animation: spin 0.8s linear infinite;
      }
      table.kv {
        width: 100%;
        border-collapse: collapse;
        font-size: 14px;
      }
      table.kv th, table.kv td {
        text-align: left;
        border-bottom: 1px solid #ecf2f9;
        padding: 8px 10px;
        vertical-align: top;
        word-break: break-word;
        white-space: pre-wrap;
      }
      table.kv th { width: 42%; color: #334155; }
      .value-good { color: var(--ok); font-weight: 600; }
      .value-warn { color: var(--warn); font-weight: 600; }
      .value-bad { color: var(--bad); font-weight: 600; }
      .runline {
        display: flex;
        align-items: center;
        gap: 10px;
        margin-bottom: 10px;
      }
      .conn-hero {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 10px 12px;
        border: 1px solid #dbe8f8;
        border-radius: 12px;
        background: #f8fbff;
        margin-bottom: 10px;
      }
      .conn-title {
        font-size: 15px;
        font-weight: 700;
      }
      .conn-detail {
        font-size: 12px;
        color: var(--muted);
      }
      .pulse-dot {
        width: 12px;
        height: 12px;
        border-radius: 999px;
        position: relative;
        flex-shrink: 0;
        color: #64748b;
        background: #64748b;
      }
      .pulse-dot::after {
        content: "";
        position: absolute;
        inset: -4px;
        border-radius: 999px;
        background: currentColor;
        opacity: 0.25;
        animation: pulseDot 1.6s ease-out infinite;
      }
      .pulse-dot.ok { color: #16a34a; background: #16a34a; }
      .pulse-dot.warn { color: #d97706; background: #d97706; }
      .pulse-dot.bad { color: #dc2626; background: #dc2626; }
      .pulse-dot.loading { color: #2563eb; background: #2563eb; }
      .pulse-dot.micro {
        width: 10px;
        height: 10px;
      }
      .pulse-dot.micro::after {
        inset: -3px;
      }
      .badge {
        border-radius: 999px;
        padding: 3px 10px;
        font-size: 12px;
        font-weight: 700;
      }
      .badge.idle { background: #e2e8f0; color: #334155; }
      .badge.running { background: #ffedd5; color: #9a3412; }
      .badge.success { background: #dcfce7; color: #166534; }
      .badge.failed { background: #fee2e2; color: #991b1b; }
      .tree-toolbar {
        display: flex;
        gap: 10px;
        flex-wrap: wrap;
        margin-bottom: 10px;
        align-items: center;
      }
      .chips {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        margin-bottom: 10px;
      }
      .chip {
        border: 1px solid #bfd3ee;
        border-radius: 999px;
        background: #f8fbff;
        padding: 4px 10px;
        font-size: 12px;
      }
      .tree-wrap {
        border: 1px solid #d8e4f3;
        border-radius: 12px;
        background: linear-gradient(180deg, #f9fcff 0%, #f4f9ff 100%);
        padding: 10px;
        max-height: 520px;
        overflow: auto;
      }
      .tree-wrap ul {
        margin: 4px 0 0 16px;
        padding: 0;
        border-left: 1px dashed #cbdbf1;
      }
      .tree-wrap li {
        list-style: none;
        margin: 4px 0;
        padding-left: 8px;
      }
      .tree-row {
        display: flex;
        align-items: center;
        gap: 8px;
        border-radius: 8px;
        padding: 3px 4px;
      }
      .tree-row:hover {
        background: #eaf2ff;
      }
      .tree-toggle {
        border: 1px solid #bfdbfe;
        background: #eff6ff;
        color: #1d4ed8;
        font-weight: 700;
        width: 18px;
        min-width: 18px;
        height: 18px;
        padding: 0;
        line-height: 16px;
        border-radius: 999px;
        cursor: pointer;
      }
      .tree-toggle:hover {
        background: #dbeafe;
      }
      .tree-toggle.placeholder {
        visibility: hidden;
      }
      .tree-type {
        min-width: 42px;
        text-align: center;
        border-radius: 999px;
        font-size: 11px;
        padding: 1px 8px;
      }
      .tree-type.folder {
        background: #dbeafe;
        color: #1e3a8a;
      }
      .tree-type.file {
        background: #e2e8f0;
        color: #334155;
      }
      .tree-name { font-size: 14px; color: #0f172a; }
      .tree-meta { font-size: 12px; color: #64748b; }
      li[data-kind="folder"] > .tree-row .tree-name {
        font-weight: 600;
      }
      .tree-collapsed > ul {
        display: none;
      }
      .doc-grid {
        display: grid;
        gap: 12px;
        grid-template-columns: 1.2fr 1fr;
      }
      .doc-note {
        border: 1px solid #bfdbfe;
        background: #eff6ff;
        color: #1e3a8a;
        border-radius: 10px;
        padding: 8px 10px;
        font-size: 13px;
        margin-bottom: 8px;
      }
      .cmd-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 13px;
      }
      .cmd-table th, .cmd-table td {
        border-bottom: 1px solid #e7eef8;
        padding: 8px 10px;
        text-align: left;
        vertical-align: top;
      }
      .cmd-table th {
        color: #1f3b64;
        background: #f8fbff;
      }
      .cmd-table td code {
        word-break: break-word;
      }
      .logs {
        margin: 0;
        background: #0f172a;
        color: #e2e8f0;
        border-radius: 12px;
        padding: 10px;
        max-height: 400px;
        overflow: auto;
        white-space: pre-wrap;
        word-break: break-word;
      }
      @media (max-width: 1024px) {
        .stats-grid {
          grid-template-columns: 1fr 1fr;
        }
        .doc-grid {
          grid-template-columns: 1fr;
        }
        .grid.two,
        .form-grid {
          grid-template-columns: 1fr;
        }
      }
      @keyframes spin {
        from { transform: rotate(0deg); }
        to { transform: rotate(360deg); }
      }
      @keyframes pulseDot {
        0% { transform: scale(1); opacity: 0.3; }
        70% { transform: scale(2.3); opacity: 0; }
        100% { transform: scale(2.3); opacity: 0; }
      }
    </style>
  </head>
  <body>
    <div class="app">
      <div class="header">
        <div>
          <h1>Drive 文件型同步控制台</h1>
          <p class="subtitle">
            统一控制台：配置接入、Drive 文件树、运行状态、定时同步、日志巡检
          </p>
        </div>
        <div class="header-actions">
          <button class="secondary" id="btnRefreshAllTop">刷新全部</button>
          <button class="secondary" id="btnGoRuntime">跳到运行状态</button>
        </div>
      </div>

      __SCOPE_BANNER__
      <div id="globalMsg" class="global-msg info">准备就绪。</div>
      <div class="stats-grid">
        <div class="stat-card">
          <div class="stat-label">飞书连接</div>
          <div class="stat-value-wrap">
            <span id="topFeishuDot" class="pulse-dot micro loading"></span>
            <div id="topFeishuState" class="stat-value">检测中</div>
          </div>
        </div>
        <div class="stat-card"><div class="stat-label">自动同步</div><div id="topAutoSyncState" class="stat-value">检测中</div></div>
        <div class="stat-card"><div class="stat-label">服务状态</div><div id="topServiceState" class="stat-value">检测中</div></div>
        <div class="stat-card"><div class="stat-label">最近同步</div><div id="topLastRunState" class="stat-value">待加载</div></div>
      </div>

      <div class="tabs">
        <button class="tab active" data-tab="config">接入配置</button>
        <button class="tab" data-tab="drive">Drive 文件树</button>
        <button class="tab" data-tab="runtime">运行状态</button>
        <button class="tab" data-tab="logs">日志巡检</button>
      </div>

      <section class="panel active" id="panel-config">
        <div class="grid two">
          <article class="card">
            <h2>初次配置（Feishu OpenAPI 术语）</h2>
            <ol class="flow">
              <li>配置应用凭证：<code>app_id</code>、<code>app_secret</code>。</li>
              <li>保存基础配置（含 <code>user_token_file</code>、Web 绑定与自动同步间隔）。</li>
              <li>生成授权地址（<code>/api/auth/url</code>）。</li>
              <li>在飞书授权后，填写 <code>code</code> 执行交换（<code>/api/auth/exchange</code>）。</li>
              <li>必要时主动刷新 <code>user_access_token</code>（<code>/api/auth/refresh</code>）。</li>
            </ol>

            <form id="cfgForm" class="form-grid">
              <label>App ID（auth.app_id）
                <input id="fAppId" value="__AUTH_APP_ID__" autocomplete="off" />
              </label>
              <label>App Secret（auth.app_secret）
                <input id="fAppSecret" type="password" value="__AUTH_APP_SECRET__" autocomplete="off" />
              </label>
              <label class="full">User Token File（auth.user_token_file）
                <input id="fUserTokenFile" value="__AUTH_USER_TOKEN_FILE__" autocomplete="off" />
              </label>
              <label>Web Bind Host（web_bind_host）
                <input id="fWebHost" value="__WEB_BIND_HOST__" autocomplete="off" />
              </label>
              <label>Web Port（web_port）
                <input id="fWebPort" value="__WEB_PORT__" autocomplete="off" />
              </label>
              <label>自动同步间隔（sync.poll_interval_sec，秒）
                <input id="fPollIntervalSec" value="300" autocomplete="off" />
                <div class="hint">0 表示关闭自动同步；推荐 300-900 秒。</div>
              </label>
              <label>间隔预设
                <select id="fPollIntervalPreset">
                  <option value="">手动输入</option>
                  <option value="60">1 分钟（调试）</option>
                  <option value="300">5 分钟（推荐）</option>
                  <option value="900">15 分钟</option>
                  <option value="1800">30 分钟</option>
                  <option value="0">关闭自动同步</option>
                </select>
              </label>
              <label class="full">Remote Folder Token（sync.remote_folder_token，可空）
                <input id="fRemoteFolderToken" autocomplete="off" />
              </label>
              <label class="full">redirect_uri（授权回调地址）
                <input id="fRedirectUri" value="https://open.feishu.cn/connect/confirm_success" autocomplete="off" />
              </label>
              <label class="full">code（授权后回填）
                <input id="fAuthCode" autocomplete="off" />
              </label>
            </form>

            <div class="actions" style="margin-top:10px;">
              <button id="btnSaveConfig">保存基础配置</button>
              <button class="secondary" id="btnAuthUrl">生成授权链接</button>
              <button class="secondary" id="btnExchangeCode">提交 code 交换 token</button>
              <button class="secondary" id="btnRefreshToken">刷新 user_access_token</button>
            </div>
            <div id="configState" class="action-state" style="margin-top:8px;">等待配置操作</div>

            <label style="margin-top:10px;">
              auth_url
              <textarea id="authUrlBox" readonly placeholder="点击“生成授权链接”后展示"></textarea>
            </label>
          </article>

          <article class="card">
            <h2>当前配置查看</h2>
            <p class="muted small">
              数据源：<code>/api/config</code>，固定本地根目录：<code>__FIXED_LOCAL_ROOT__</code>
            </p>
            <table class="kv" id="configTable">
              <tbody>
                <tr><th>状态</th><td>待加载</td></tr>
              </tbody>
            </table>
          </article>
        </div>

        <article class="card" style="margin-top:14px;">
          <h2>使用说明与 CLI 命令表</h2>
          <div class="doc-grid">
            <div>
              <div class="doc-note">从零开始推荐流程：先配置并授权，再检查状态，最后开启自动同步或手动触发同步。</div>
              <ol class="flow">
                <li>在本页填写 <code>app_id</code>、<code>app_secret</code>、<code>user_token_file</code>，点击“保存基础配置”。</li>
                <li>点击“生成授权链接”，在飞书完成授权后，把 code 回填并点击“提交 code 交换 token”。</li>
                <li>切到“运行状态”，确认飞书连接为正常（绿灯）且服务状态为运行中。</li>
                <li>设置自动同步间隔（<code>sync.poll_interval_sec</code>）：<code>0</code> 关闭，推荐 <code>300</code> 秒。</li>
                <li>需要立刻执行时，点击“执行一次同步”，并在“日志巡检”查看细节。</li>
              </ol>
              <p class="muted small">CLI 帮助信息：支持，运行 <code>python -m localfilesync.cli.main --help</code> 或 <code>python -m localfilesync.cli.main [命令] --help</code>。</p>
            </div>
            <div>
              <table class="cmd-table">
                <thead>
                  <tr><th>CLI 命令</th><th>用途</th></tr>
                </thead>
                <tbody>
                  <tr><td><code>python -m localfilesync.cli.main --help</code></td><td>查看所有命令总览与参数说明</td></tr>
                  <tr><td><code>python -m localfilesync.cli.main status</code></td><td>查看运行状态、服务状态、自动同步配置</td></tr>
                  <tr><td><code>python -m localfilesync.cli.main config-validate</code></td><td>验证配置完整性与路径可用性</td></tr>
                  <tr><td><code>python -m localfilesync.cli.main auth-url</code></td><td>生成飞书授权链接</td></tr>
                  <tr><td><code>python -m localfilesync.cli.main auth-exchange --code &lt;CODE&gt;</code></td><td>用授权码交换 user token</td></tr>
                  <tr><td><code>python -m localfilesync.cli.main auth-refresh --force</code></td><td>强制刷新 user_access_token</td></tr>
                  <tr><td><code>python -m localfilesync.cli.main run-once --dry-run</code></td><td>执行本地预检，不做远端改动</td></tr>
                  <tr><td><code>python -m localfilesync.cli.main run-once</code></td><td>执行一次真实同步</td></tr>
                  <tr><td><code>python -m localfilesync.cli.main logs-tail --n 100 --level INFO</code></td><td>查看并过滤服务日志</td></tr>
                  <tr><td><code>python -m localfilesync.cli.main service-status</code></td><td>查看 systemd 用户服务状态</td></tr>
                  <tr><td><code>python -m localfilesync.cli.main service-restart</code></td><td>重启服务进程</td></tr>
                </tbody>
              </table>
            </div>
          </div>
        </article>
      </section>

      <section class="panel" id="panel-drive">
        <article class="card">
          <h2>Drive 目录 + 文件树</h2>
          <div class="tree-toolbar">
            <label style="display:flex;align-items:center;gap:6px;">
              depth
              <select id="treeDepth" style="width:92px;margin:0;">
                <option value="2">2</option>
                <option value="3" selected>3</option>
                <option value="4">4</option>
                <option value="5">5</option>
                <option value="6">6</option>
              </select>
            </label>
            <label style="display:flex;align-items:center;gap:6px;">
              <input id="treeIncludeRecycle" type="checkbox" style="width:auto;margin:0;" />
              包含回收目录（SyncRecycleBin）
            </label>
            <button class="secondary" id="btnRefreshTree">刷新 Drive 树</button>
            <button class="secondary" id="btnExpandAllTree">全部展开</button>
            <button class="secondary" id="btnCollapseAllTree">全部折叠</button>
          </div>
          <div id="treeState" class="action-state">等待刷新</div>

          <div class="chips">
            <span class="chip">token_type: <code id="treeTokenType">-</code></span>
            <span class="chip">root_folder_token: <code id="treeRootToken">-</code></span>
            <span class="chip">folders: <code id="treeFolderCount">0</code></span>
            <span class="chip">files: <code id="treeFileCount">0</code></span>
            <span class="chip">truncated: <code id="treeTruncatedCount">0</code></span>
          </div>

          <div class="tree-wrap" id="driveTree">待加载 Drive 树...</div>
        </article>
      </section>

      <section class="panel" id="panel-runtime">
        <div class="grid two">
          <article class="card">
            <h2>飞书连接状态</h2>
            <div class="conn-hero">
              <span id="feishuLampDot" class="pulse-dot loading"></span>
              <div>
                <div id="feishuLampTitle" class="conn-title">连接检测中</div>
                <div id="feishuLampDetail" class="conn-detail">等待首次检查...</div>
              </div>
            </div>
            <table class="kv" id="feishuTable">
              <tbody>
                <tr><th>状态</th><td>待加载</td></tr>
              </tbody>
            </table>
          </article>

          <article class="card">
            <h2>服务状态 + 手动同步</h2>
            <div class="runline">
              <span id="runBadge" class="badge idle">空闲</span>
              <span id="runBadgeText" class="muted">尚未触发本轮同步</span>
            </div>
            <div class="actions" style="margin-bottom:10px;">
              <button id="btnRunOnce">执行一次同步</button>
              <button class="warn" id="btnRestartService">重启服务</button>
              <button class="secondary" id="btnRefreshRuntime">刷新本区</button>
              <button class="secondary" id="btnViewLastRunDetail">查看异常详情</button>
              <button class="secondary" id="btnClearLastRunError">清空最近异常</button>
            </div>
            <div id="runtimeState" class="action-state" style="margin-bottom:10px;">等待刷新</div>

            <h3>Service 状态（systemd）</h3>
            <table class="kv" id="serviceTable">
              <tbody>
                <tr><th>状态</th><td>待加载</td></tr>
              </tbody>
            </table>

            <h3>自动同步调度状态</h3>
            <table class="kv" id="schedulerTable">
              <tbody>
                <tr><th>状态</th><td>待加载</td></tr>
              </tbody>
            </table>

            <h3>最近一次同步摘要</h3>
            <table class="kv" id="runSummaryTable">
              <tbody>
                <tr><th>状态</th><td>待加载（__LAST_RUN_PATH__）</td></tr>
              </tbody>
            </table>
          </article>
        </div>
      </section>

      <section class="panel" id="panel-logs">
        <article class="card">
          <h2>日志查看</h2>
          <div class="actions" style="margin-bottom:10px;">
            <label style="display:flex;align-items:center;gap:6px;">
              n
              <input id="logN" value="200" style="width:90px;margin:0;" />
            </label>
            <label style="display:flex;align-items:center;gap:6px;">
              level
              <select id="logLevel" style="width:130px;margin:0;">
                <option value="">全部</option>
                <option value="DEBUG">DEBUG</option>
                <option value="INFO">INFO</option>
                <option value="WARNING">WARNING</option>
                <option value="ERROR">ERROR</option>
                <option value="CRITICAL">CRITICAL</option>
              </select>
            </label>
            <label style="display:flex;align-items:center;gap:6px;min-width:260px;">
              module
              <input id="logModule" placeholder="例如 sync / uvicorn.error / scheduler" style="margin:0;" />
            </label>
            <button class="secondary" id="btnRefreshLogs">刷新日志</button>
          </div>
          <div id="logsState" class="action-state" style="margin-bottom:8px;">等待刷新</div>
          <pre class="logs" id="logPane">待加载日志...</pre>
        </article>
      </section>
    </div>

    <script>
      const OUT_OF_SCOPE = __OUT_OF_SCOPE__;
      const LAST_RUN_PATH = "__LAST_RUN_PATH__";
      let autoSyncEnabled = false;
      let autoSyncLastResult = "";
      let autoSyncNextRunInSec = null;
      let autoSyncTicker = null;

      function asText(value, fallback) {
        if (value === null || value === undefined) return fallback || "-";
        const s = String(value).trim();
        return s || (fallback || "-");
      }

      function asYesNo(value) {
        if (value === null || value === undefined) return "未知";
        return value ? "是" : "否";
      }

      function escapeHtml(value) {
        return String(value)
          .replace(/&/g, "&amp;")
          .replace(/</g, "&lt;")
          .replace(/>/g, "&gt;");
      }

      function toLocalTime(value) {
        if (!value) return "-";
        try {
          return new Date(value).toLocaleString("zh-CN", { hour12: false });
        } catch (_e) {
          return String(value);
        }
      }

      function bytes(v) {
        const n = Number(v || 0);
        if (!Number.isFinite(n) || n <= 0) return "0 B";
        if (n < 1024) return n + " B";
        if (n < 1024 * 1024) return (n / 1024).toFixed(1) + " KB";
        if (n < 1024 * 1024 * 1024) return (n / (1024 * 1024)).toFixed(1) + " MB";
        return (n / (1024 * 1024 * 1024)).toFixed(1) + " GB";
      }

      function tErr(raw) {
        const s = asText(raw, "");
        if (!s) return "无";
        if (s.indexOf("no_available_token") >= 0 || s.indexOf("no_token") >= 0) return "没有可用令牌，请先完成 app_id/app_secret 与授权。";
        if (s.indexOf("oauth_code_missing") >= 0) return "缺少授权 code。";
        if (s.indexOf("auth_incomplete") >= 0) return "应用凭证不完整，请检查 app_id 与 app_secret。";
        if (s.indexOf("invalid_config") >= 0) return "配置格式不合法，请检查端口和自动同步间隔。";
        if (s.indexOf("sync_busy") >= 0) return "同步任务正在执行中，请稍后重试。";
        if (s.indexOf("feishu_error") >= 0) return "飞书 OpenAPI 返回错误，请检查权限范围。";
        if (s.indexOf("Failed to fetch") >= 0) return "请求失败，请确认服务已启动。";
        if (s.indexOf("timed out") >= 0 || s.indexOf("timeout") >= 0) return "请求超时，请稍后重试。";
        return s;
      }

      function setMsg(text, level) {
        const node = document.getElementById("globalMsg");
        node.textContent = text;
        node.className = "global-msg " + (level || "info");
      }

      function nowClock() {
        return new Date().toLocaleTimeString("zh-CN", { hour12: false });
      }

      function setActionState(nodeId, text, tone) {
        const node = document.getElementById(nodeId);
        if (!node) return;
        node.textContent = text;
        node.className = "action-state" + (tone ? (" " + tone) : "");
      }

      function setTopStat(nodeId, text, tone) {
        const node = document.getElementById(nodeId);
        if (!node) return;
        node.textContent = text;
        node.className = "stat-value" + (tone ? (" " + tone) : "");
      }

      function shortToken(value, left, right) {
        const s = asText(value, "-");
        const l = Number(left || 7);
        const r = Number(right || 5);
        if (s === "-" || s.length <= l + r + 3) return s;
        return s.slice(0, l) + "..." + s.slice(-r);
      }

      function setFeishuLamp(mode, title, detail) {
        const safeMode = ["loading", "ok", "warn", "bad"].includes(mode) ? mode : "loading";
        const dot = document.getElementById("feishuLampDot");
        const topDot = document.getElementById("topFeishuDot");
        const titleNode = document.getElementById("feishuLampTitle");
        const detailNode = document.getElementById("feishuLampDetail");
        dot.className = "pulse-dot " + safeMode;
        if (topDot) topDot.className = "pulse-dot micro " + safeMode;
        titleNode.textContent = title || "连接检测中";
        detailNode.textContent = detail || "";
      }

      async function withButtonLoading(btnId, pendingText, fn) {
        const btn = document.getElementById(btnId);
        if (!btn) return fn();
        const origin = btn.dataset.originText || btn.textContent;
        if (!btn.dataset.originText) btn.dataset.originText = origin;
        btn.disabled = true;
        btn.classList.add("btn-loading");
        btn.textContent = pendingText || "处理中...";
        try {
          return await fn();
        } finally {
          btn.disabled = false;
          btn.classList.remove("btn-loading");
          btn.textContent = btn.dataset.originText || origin;
        }
      }

      function bindButtonAction(btnId, pendingText, fn) {
        const btn = document.getElementById(btnId);
        if (!btn) return;
        btn.addEventListener("click", (event) => {
          event.preventDefault();
          withButtonLoading(btnId, pendingText, fn).catch((err) => {
            setMsg("操作失败：" + tErr(err && err.message ? err.message : err), "danger");
          });
        });
      }

      function renderRows(tableId, rows) {
        const tbody = document.querySelector("#" + tableId + " tbody");
        tbody.innerHTML = rows.map((row) => {
          const cls = row[2] ? (" class='" + escapeHtml(row[2]) + "'") : "";
          return "<tr><th>" + escapeHtml(asText(row[0])) + "</th><td" + cls + ">" + escapeHtml(asText(row[1])) + "</td></tr>";
        }).join("");
      }

      async function api(method, url, payload) {
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
          throw new Error(data.detail || data.error || data.raw || ("HTTP " + resp.status));
        }
        return data;
      }

      function activateTab(name) {
        document.querySelectorAll(".tab").forEach((tab) => {
          tab.classList.toggle("active", tab.dataset.tab === name);
        });
        document.querySelectorAll(".panel").forEach((panel) => {
          panel.classList.toggle("active", panel.id === ("panel-" + name));
        });
      }

      function setRunBadge(state, text) {
        const badge = document.getElementById("runBadge");
        const label = document.getElementById("runBadgeText");
        badge.className = "badge " + state;
        if (state === "running") badge.textContent = "执行中";
        else if (state === "success") badge.textContent = "成功";
        else if (state === "failed") badge.textContent = "失败";
        else badge.textContent = "空闲";
        label.textContent = text || "";
      }

      async function refreshConfigView(options) {
        const silentState = !!(options && options.silentState);
        if (!silentState) setActionState("configState", "正在读取当前配置...", "loading");
        try {
          const data = await api("GET", "/api/config");
          const scope = data._scope || {};
          const out = !!scope.out_of_scope;

          document.getElementById("fAppId").value = asText(data.auth && data.auth.app_id, "");
          document.getElementById("fAppSecret").value = asText(data.auth && data.auth.app_secret, "");
          document.getElementById("fUserTokenFile").value = asText(data.auth && data.auth.user_token_file, "");
          document.getElementById("fWebHost").value = asText(data.web_bind_host, "127.0.0.1");
          document.getElementById("fWebPort").value = asText(data.web_port, "8765");
          const pollIntervalValue = asText(data.sync && data.sync.poll_interval_sec, "300");
          document.getElementById("fPollIntervalSec").value = pollIntervalValue;
          const preset = document.getElementById("fPollIntervalPreset");
          if (Array.from(preset.options).some((opt) => opt.value === pollIntervalValue)) preset.value = pollIntervalValue;
          else preset.value = "";
          document.getElementById("fRemoteFolderToken").value = asText(data.sync && data.sync.remote_folder_token, "");

          const schedulerMeta = data._scheduler || {};
          const configuredInterval = Number(data.sync && data.sync.poll_interval_sec || 0);
          const effectiveInterval = Number(schedulerMeta.effective_poll_interval_sec || configuredInterval || 0);
          const rows = [
            ["固定本地根目录", asText(scope.fixed_local_root), "value-good"],
            ["配置中的 local_root", asText(scope.configured_local_root), out ? "value-warn" : ""],
            ["out_of_scope", out ? "是" : "否", out ? "value-warn" : "value-good"],
            ["auth.app_id", asText(data.auth && data.auth.app_id), (data.auth && data.auth.app_id) ? "value-good" : "value-bad"],
            ["auth.app_secret", (data.auth && data.auth.app_secret) ? "已配置（隐藏）" : "未配置", (data.auth && data.auth.app_secret) ? "value-good" : "value-bad"],
            ["auth.user_token_file", asText(data.auth && data.auth.user_token_file), ""],
            ["sync.remote_folder_token", asText(data.sync && data.sync.remote_folder_token, "未配置（默认 Drive 根目录）"), ""],
            ["sync.auto_sync_enabled", configuredInterval > 0 ? "是" : "否", configuredInterval > 0 ? "value-good" : "value-warn"],
            ["sync.poll_interval_sec", asText(configuredInterval), configuredInterval > 0 ? "" : "value-warn"],
            ["sync.poll_interval_effective_sec", asText(effectiveInterval), (configuredInterval > 0 && effectiveInterval !== configuredInterval) ? "value-warn" : ""],
            ["web_bind_host:web_port", asText(data.web_bind_host) + ":" + asText(data.web_port), ""],
            ["database.path", asText(data.database && data.database.path), ""],
            ["logging.file", asText(data.logging && data.logging.file), ""]
          ];
          renderRows("configTable", rows);
          if (!silentState) setActionState("configState", "当前配置已刷新（" + nowClock() + "）", "success");
          return true;
        } catch (err) {
          renderRows("configTable", [
            ["状态", "读取失败", "value-bad"],
            ["错误", tErr(err.message), "value-bad"]
          ]);
          if (!silentState) setActionState("configState", "读取配置失败：" + tErr(err.message), "danger");
          setMsg("读取配置失败：" + tErr(err.message), "danger");
          return false;
        }
      }

      async function saveConfig() {
        setActionState("configState", "正在保存基础配置...", "loading");
        const pollIntervalRaw = document.getElementById("fPollIntervalSec").value.trim();
        const pollInterval = Number(pollIntervalRaw || "300");
        if (!Number.isFinite(pollInterval) || pollInterval < 0) {
          setActionState("configState", "自动同步间隔必须是大于等于 0 的数字。", "warn");
          setMsg("自动同步间隔必须是大于等于 0 的数字。", "warn");
          return false;
        }
        const payload = {
          auth: {
            app_id: document.getElementById("fAppId").value.trim(),
            app_secret: document.getElementById("fAppSecret").value.trim(),
            user_token_file: document.getElementById("fUserTokenFile").value.trim()
          },
          sync: {
            remote_folder_token: document.getElementById("fRemoteFolderToken").value.trim(),
            poll_interval_sec: Math.floor(pollInterval)
          },
          web_bind_host: document.getElementById("fWebHost").value.trim(),
          web_port: Number(document.getElementById("fWebPort").value.trim() || "8765")
        };
        try {
          const result = await api("POST", "/api/config", payload);
          if (result.warnings && result.warnings.length > 0) {
            setMsg("配置已保存，local_root 超范围时会自动锁定。", "warn");
            setActionState("configState", "配置已保存（含提示，" + nowClock() + "）", "warn");
          } else {
            setMsg("配置已保存。", "success");
            setActionState("configState", "配置保存成功（" + nowClock() + "）", "success");
          }
          await refreshConfigView({ silentState: true });
          await Promise.all([refreshFeishu(), refreshScheduler()]);
          return true;
        } catch (err) {
          setActionState("configState", "保存配置失败：" + tErr(err.message), "danger");
          setMsg("保存配置失败：" + tErr(err.message), "danger");
          return false;
        }
      }

      async function genAuthUrl() {
        setActionState("configState", "正在生成授权链接...", "loading");
        const redirectUri = document.getElementById("fRedirectUri").value.trim();
        if (!redirectUri) {
          setActionState("configState", "请先填写 redirect_uri。", "warn");
          setMsg("请先填写 redirect_uri。", "warn");
          return false;
        }
        try {
          const data = await api("GET", "/api/auth/url?redirect_uri=" + encodeURIComponent(redirectUri));
          if (!data.ok) throw new Error(data.error || "生成授权链接失败");
          document.getElementById("authUrlBox").value = asText(data.auth_url, "");
          setActionState("configState", "授权链接已生成（" + nowClock() + "）", "success");
          setMsg("授权链接已生成，请在浏览器打开并完成授权。", "success");
          return true;
        } catch (err) {
          setActionState("configState", "生成授权链接失败：" + tErr(err.message), "danger");
          setMsg("生成授权链接失败：" + tErr(err.message), "danger");
          return false;
        }
      }

      async function exchangeCode() {
        setActionState("configState", "正在提交授权 code...", "loading");
        const code = document.getElementById("fAuthCode").value.trim();
        if (!code) {
          setActionState("configState", "请先填写授权 code。", "warn");
          setMsg("请填写授权 code。", "warn");
          return false;
        }
        try {
          const data = await api("POST", "/api/auth/exchange", { code: code });
          if (!data.ok) throw new Error(data.error || "交换失败");
          document.getElementById("fAuthCode").value = "";
          setActionState("configState", "授权 code 交换成功（" + nowClock() + "）", "success");
          setMsg("code 交换成功，token_type=" + asText(data.token_type) + " expires_in=" + asText(data.expires_in), "success");
          await refreshFeishu();
          return true;
        } catch (err) {
          setActionState("configState", "code 交换失败：" + tErr(err.message), "danger");
          setMsg("code 交换失败：" + tErr(err.message), "danger");
          return false;
        }
      }

      async function refreshToken() {
        setActionState("configState", "正在刷新 user_access_token...", "loading");
        try {
          const data = await api("POST", "/api/auth/refresh?force=true", {});
          if (!data.ok) throw new Error(data.error || "刷新失败");
          setActionState("configState", "user_access_token 刷新成功（" + nowClock() + "）", "success");
          setMsg("user_access_token 已刷新。expires_in=" + asText(data.expires_in), "success");
          await refreshFeishu();
          return true;
        } catch (err) {
          setActionState("configState", "刷新 user_access_token 失败：" + tErr(err.message), "danger");
          setMsg("刷新 user_access_token 失败：" + tErr(err.message), "danger");
          return false;
        }
      }

      function renderTree(tree) {
        const root = document.getElementById("driveTree");
        if (!tree) {
          root.innerHTML = "<div class='muted small'>暂无数据</div>";
          return;
        }
        root.innerHTML = "";
        const ul = document.createElement("ul");
        ul.appendChild(renderTreeNode(tree, true, 0));
        root.appendChild(ul);
      }

      function setTreeCollapsed(treeNode, collapsed) {
        if (!treeNode || treeNode.dataset.expandable !== "1") return;
        treeNode.classList.toggle("tree-collapsed", collapsed);
        const toggle = treeNode.querySelector(".tree-row .tree-toggle");
        if (toggle) {
          toggle.textContent = collapsed ? "+" : "−";
          toggle.title = collapsed ? "展开目录" : "折叠目录";
        }
      }

      function renderTreeNode(node, isRoot, depth) {
        const li = document.createElement("li");
        const isFolder = node.type === "folder";
        const children = Array.isArray(node.children) ? node.children : [];
        const expandable = isFolder && children.length > 0;
        li.dataset.kind = isFolder ? "folder" : "file";
        if (expandable) li.dataset.expandable = "1";

        const row = document.createElement("div");
        row.className = "tree-row";

        if (expandable) {
          const toggle = document.createElement("button");
          toggle.type = "button";
          toggle.className = "tree-toggle";
          toggle.textContent = "−";
          toggle.title = "折叠目录";
          toggle.addEventListener("click", (event) => {
            event.preventDefault();
            event.stopPropagation();
            setTreeCollapsed(li, !li.classList.contains("tree-collapsed"));
          });
          row.appendChild(toggle);
          row.style.cursor = "pointer";
          row.addEventListener("click", () => {
            setTreeCollapsed(li, !li.classList.contains("tree-collapsed"));
          });
        } else {
          const toggle = document.createElement("span");
          toggle.className = "tree-toggle placeholder";
          toggle.textContent = "·";
          row.appendChild(toggle);
        }

        const type = document.createElement("span");
        type.className = "tree-type " + (isFolder ? "folder" : "file");
        type.textContent = isFolder ? "目录" : "文件";
        row.appendChild(type);

        const name = document.createElement("span");
        name.className = "tree-name";
        name.textContent = isRoot ? "/ " + asText(node.name, "drive_root") : asText(node.name, "(unnamed)");
        row.appendChild(name);

        const meta = document.createElement("span");
        meta.className = "tree-meta";
        if (isFolder) {
          meta.textContent = "子项 " + children.length + (node.truncated ? " · 深度已截断" : "") + " · ID " + shortToken(node.token, 6, 4);
        } else {
          meta.textContent = "大小 " + bytes(node.size) + " · ID " + shortToken(node.token, 6, 4);
        }
        row.appendChild(meta);
        if (node.token || node.path) {
          const hints = [];
          if (node.path) hints.push("path: " + asText(node.path));
          if (node.token) hints.push("token: " + asText(node.token));
          row.title = hints.join("\\n");
        }
        li.appendChild(row);

        if (expandable) {
          const ul = document.createElement("ul");
          for (const c of children) ul.appendChild(renderTreeNode(c, false, depth + 1));
          li.appendChild(ul);
          if (depth >= 2) setTreeCollapsed(li, true);
        }
        return li;
      }

      function expandAllTree() {
        const nodes = Array.from(document.querySelectorAll("#driveTree li[data-expandable='1']"));
        if (nodes.length === 0) {
          setActionState("treeState", "没有可展开目录，请先刷新 Drive 树。", "warn");
          return false;
        }
        nodes.forEach((node) => setTreeCollapsed(node, false));
        setActionState("treeState", "目录树已全部展开（" + nodes.length + " 个目录，" + nowClock() + "）", "success");
        return true;
      }

      function collapseAllTree() {
        const nodes = Array.from(document.querySelectorAll("#driveTree li[data-expandable='1']"));
        if (nodes.length === 0) {
          setActionState("treeState", "没有可折叠目录，请先刷新 Drive 树。", "warn");
          return false;
        }
        nodes.forEach((node) => setTreeCollapsed(node, true));
        setActionState("treeState", "目录树已全部折叠（" + nodes.length + " 个目录，" + nowClock() + "）", "success");
        return true;
      }

      async function refreshTree() {
        setActionState("treeState", "正在刷新 Drive 树...", "loading");
        document.getElementById("driveTree").textContent = "正在读取 Drive 树...";
        const depth = Number(document.getElementById("treeDepth").value || "3");
        const includeRecycle = document.getElementById("treeIncludeRecycle").checked;
        try {
          const url = "/api/drive/tree?depth=" + encodeURIComponent(depth) + "&include_recycle_bin=" + (includeRecycle ? "true" : "false");
          const data = await api("GET", url);
          if (!data.ok) throw new Error(data.error || "获取 Drive 树失败");

          document.getElementById("treeTokenType").textContent = asText(data.token_type);
          const rootToken = asText(data.root_folder_token);
          const rootTokenNode = document.getElementById("treeRootToken");
          rootTokenNode.textContent = shortToken(rootToken, 8, 6);
          rootTokenNode.title = rootToken === "-" ? "" : rootToken;
          document.getElementById("treeFolderCount").textContent = asText(data.stats && data.stats.folders, "0");
          document.getElementById("treeFileCount").textContent = asText(data.stats && data.stats.files, "0");
          document.getElementById("treeTruncatedCount").textContent = asText(data.stats && data.stats.truncated_nodes, "0");
          renderTree(data.tree || null);
          setActionState(
            "treeState",
            "Drive 树已刷新（目录 " + asText(data.stats && data.stats.folders, "0") + "，文件 " + asText(data.stats && data.stats.files, "0") + "，" + nowClock() + "）",
            "success",
          );
          return true;
        } catch (err) {
          document.getElementById("driveTree").textContent = "读取 Drive 树失败：" + tErr(err.message);
          setActionState("treeState", "读取 Drive 树失败：" + tErr(err.message), "danger");
          setMsg("读取 Drive 树失败：" + tErr(err.message), "danger");
          return false;
        }
      }

      async function refreshFeishu() {
        setFeishuLamp("loading", "连接检测中", "正在校验 token 与 API 连通性...");
        try {
          const data = await api("GET", "/api/status/feishu");
          const errText = (data.token && data.token.error) || (data.connectivity && data.connectivity.error) || "";
          const rows = [
            ["checked_at", toLocalTime(data.checked_at), ""],
            ["app_id_configured", asYesNo(data.config && data.config.app_id_configured), (data.config && data.config.app_id_configured) ? "value-good" : "value-bad"],
            ["app_secret_configured", asYesNo(data.config && data.config.app_secret_configured), (data.config && data.config.app_secret_configured) ? "value-good" : "value-bad"],
            ["user_token_file", asText(data.config && data.config.user_token_file), ""],
            ["user_token_file_exists", asYesNo(data.config && data.config.user_token_file_exists), (data.config && data.config.user_token_file_exists) ? "value-good" : "value-warn"],
            ["token.available", asYesNo(data.token && data.token.available), (data.token && data.token.available) ? "value-good" : "value-bad"],
            ["token.type", asText(data.token && data.token.type), ""],
            ["connectivity.api_access", asYesNo(data.connectivity && data.connectivity.api_access), (data.connectivity && data.connectivity.api_access) ? "value-good" : "value-bad"],
            ["connectivity.root_folder_token", asText(data.connectivity && data.connectivity.root_folder_token), ""],
            ["error", errText ? tErr(errText) : "无", errText ? "value-bad" : ""]
          ];
          renderRows("feishuTable", rows);
          const tokenAvailable = !!(data.token && data.token.available);
          const apiAccess = !!(data.connectivity && data.connectivity.api_access);
          const checked = toLocalTime(data.checked_at);
          if (tokenAvailable && apiAccess) {
            const rootToken = asText(data.connectivity && data.connectivity.root_folder_token, "");
            const detail = rootToken ? ("API 可访问，root_folder_token=" + shortToken(rootToken, 8, 6) + "（" + checked + "）") : ("API 可访问（" + checked + "）");
            setFeishuLamp("ok", "飞书连接正常", detail);
            setTopStat("topFeishuState", "正常", "good");
          } else if (tokenAvailable && !apiAccess) {
            setFeishuLamp("warn", "令牌可用，但 API 访问失败", errText ? tErr(errText) : "请检查 Drive 权限或网络。");
            setTopStat("topFeishuState", "告警", "warn");
          } else if ((data.config && data.config.app_id_configured) && (data.config && data.config.app_secret_configured)) {
            setFeishuLamp("warn", "应用已配置，等待授权", errText ? tErr(errText) : "未检测到可用 user_access_token。");
            setTopStat("topFeishuState", "待授权", "warn");
          } else {
            setFeishuLamp("bad", "飞书连接未就绪", "请先配置 app_id/app_secret 并完成授权。");
            setTopStat("topFeishuState", "未就绪", "bad");
          }
          return true;
        } catch (err) {
          renderRows("feishuTable", [
            ["状态", "读取失败", "value-bad"],
            ["错误", tErr(err.message), "value-bad"]
          ]);
          setFeishuLamp("bad", "连接检查失败", tErr(err.message));
          setTopStat("topFeishuState", "失败", "bad");
          setMsg("读取飞书状态失败：" + tErr(err.message), "danger");
          return false;
        }
      }

      function mapState(raw, mapping) {
        const k = asText(raw, "-");
        if (k === "-") return "-";
        return mapping[k] ? (mapping[k] + "（" + k + "）") : k;
      }

      function secText(sec) {
        const n = Number(sec);
        if (!Number.isFinite(n) || n < 0) return "-";
        const h = Math.floor(n / 3600);
        const m = Math.floor((n % 3600) / 60);
        const s = Math.floor(n % 60);
        if (h > 0) return h + "小时" + m + "分" + s + "秒";
        if (m > 0) return m + "分" + s + "秒";
        return s + "秒";
      }

      function renderAutoSyncTop() {
        if (!autoSyncEnabled) {
          setTopStat("topAutoSyncState", "关闭", "warn");
          return;
        }
        if (autoSyncLastResult === "running") {
          setTopStat("topAutoSyncState", "执行中", "info");
          return;
        }
        if (autoSyncLastResult === "failed") {
          setTopStat("topAutoSyncState", "失败", "bad");
          return;
        }
        if (autoSyncLastResult === "warning" || autoSyncLastResult === "skipped_busy") {
          const suffix = Number.isFinite(Number(autoSyncNextRunInSec)) ? (" · 下次 " + secText(autoSyncNextRunInSec)) : "";
          setTopStat("topAutoSyncState", "告警" + suffix, "warn");
          return;
        }
        if (Number.isFinite(Number(autoSyncNextRunInSec))) {
          const sec = Number(autoSyncNextRunInSec);
          if (sec <= 0) setTopStat("topAutoSyncState", "开启 · 即将执行", "info");
          else setTopStat("topAutoSyncState", "开启 · 下次 " + secText(sec), "good");
          return;
        }
        setTopStat("topAutoSyncState", "开启", "good");
      }

      function ensureAutoSyncTicker() {
        if (autoSyncTicker !== null) return;
        autoSyncTicker = window.setInterval(() => {
          if (autoSyncEnabled && autoSyncLastResult !== "running" && Number.isFinite(Number(autoSyncNextRunInSec))) {
            const sec = Number(autoSyncNextRunInSec);
            autoSyncNextRunInSec = sec > 0 ? sec - 1 : 0;
          }
          renderAutoSyncTop();
        }, 1000);
      }

      async function refreshScheduler() {
        try {
          const data = await api("GET", "/api/status/scheduler");
          const running = !!data.running;
          const enabled = !!data.enabled;
          const configuredInterval = Number(data.configured_interval_sec || 0);
          const effectiveInterval = Number(data.effective_interval_sec || 0);
          const rows = [
            ["checked_at", toLocalTime(data.checked_at), ""],
            ["scheduler_running", asYesNo(running), running ? "value-good" : "value-bad"],
            ["auto_sync_enabled", asYesNo(enabled), enabled ? "value-good" : "value-warn"],
            ["poll_interval_sec(configured)", asText(configuredInterval), enabled ? "" : "value-warn"],
            ["poll_interval_sec(effective)", asText(effectiveInterval), (enabled && configuredInterval !== effectiveInterval) ? "value-warn" : ""],
            ["next_run_at", toLocalTime(data.next_run_at), ""],
            ["next_run_in", secText(data.next_run_in_sec), ""],
            ["last_started_at", toLocalTime(data.last_started_at), ""],
            ["last_finished_at", toLocalTime(data.last_finished_at), ""],
            ["last_result", asText(data.last_result, enabled ? "waiting" : "disabled"), data.last_result === "failed" ? "value-bad" : (data.last_result === "warning" || data.last_result === "skipped_busy" ? "value-warn" : "value-good")],
            ["run_count", asText(data.run_count, "0"), ""],
            ["skipped_busy_count", asText(data.skipped_busy_count, "0"), Number(data.skipped_busy_count || 0) > 0 ? "value-warn" : ""],
            ["last_error", data.last_error ? tErr(data.last_error) : "无", data.last_error ? "value-bad" : ""]
          ];
          renderRows("schedulerTable", rows);

          autoSyncEnabled = enabled;
          autoSyncLastResult = asText(data.last_result, "");
          autoSyncNextRunInSec = Number.isFinite(Number(data.next_run_in_sec)) ? Number(data.next_run_in_sec) : null;
          renderAutoSyncTop();

          if (!enabled) {
            setRunBadge("idle", "自动同步已关闭，仅手动执行");
          } else if (data.last_result === "running") {
            setRunBadge("running", "自动同步正在执行中");
          } else if (data.last_result === "failed") {
            setRunBadge("failed", "自动同步最近一次失败");
          }
          return true;
        } catch (err) {
          renderRows("schedulerTable", [
            ["状态", "读取失败", "value-bad"],
            ["错误", tErr(err.message), "value-bad"]
          ]);
          autoSyncEnabled = false;
          autoSyncLastResult = "failed";
          autoSyncNextRunInSec = null;
          renderAutoSyncTop();
          setTopStat("topAutoSyncState", "失败", "bad");
          setMsg("读取调度状态失败：" + tErr(err.message), "danger");
          return false;
        }
      }

      async function refreshService() {
        try {
          const data = await api("GET", "/api/status/service");
          const active = asText(data.active_state, "-");
          const rows = [
            ["checked_at", toLocalTime(data.checked_at), ""],
            ["systemd_available", asYesNo(data.systemd_available), data.systemd_available ? "value-good" : "value-bad"],
            ["load_state", mapState(data.load_state, { loaded: "已加载", not_found: "未找到", masked: "已屏蔽" }), ""],
            ["active_state", mapState(active, { active: "运行中", inactive: "未运行", failed: "失败", activating: "启动中", deactivating: "停止中" }), active === "active" ? "value-good" : "value-bad"],
            ["sub_state", mapState(data.sub_state, { running: "运行中", exited: "已退出", dead: "已停止", auto_restart: "自动重启" }), ""],
            ["unit_file_state", mapState(data.unit_file_state, { enabled: "已启用", disabled: "已禁用", static: "静态", masked: "已屏蔽" }), ""],
            ["main_pid", asText(data.main_pid), ""],
            ["error", data.error ? tErr(data.error) : "无", data.error ? "value-bad" : ""]
          ];
          renderRows("serviceTable", rows);
          setTopStat("topServiceState", active === "active" ? "运行中" : asText(active, "未知"), active === "active" ? "good" : "warn");
          return true;
        } catch (err) {
          renderRows("serviceTable", [
            ["状态", "读取失败", "value-bad"],
            ["错误", tErr(err.message), "value-bad"]
          ]);
          setTopStat("topServiceState", "失败", "bad");
          setMsg("读取服务状态失败：" + tErr(err.message), "danger");
          return false;
        }
      }

      function renderRunSummary(summary) {
        if (!summary) {
          renderRows("runSummaryTable", [["状态", "暂无同步摘要（" + LAST_RUN_PATH + "）", ""]]);
          setTopStat("topLastRunState", "暂无记录", "warn");
          return;
        }
        const errors = Number(summary.errors || 0);
        const fatal = asText(summary.fatal_error, "");
        renderRows("runSummaryTable", [
          ["run_id", asText(summary.run_id), ""],
          ["local_root", asText(summary.local_root), ""],
          ["remote_root_token", asText(summary.remote_root_token), ""],
          ["local_total / remote_total", asText(summary.local_total, "0") + " / " + asText(summary.remote_total, "0"), ""],
          ["uploaded / downloaded / renamed", asText(summary.uploaded, "0") + " / " + asText(summary.downloaded, "0") + " / " + asText(summary.renamed, "0"), ""],
          ["conflicts", asText(summary.conflicts, "0"), Number(summary.conflicts || 0) > 0 ? "value-warn" : ""],
          ["retry_success / retry_failed", asText(summary.retry_success, "0") + " / " + asText(summary.retry_failed, "0"), ""],
          ["errors", asText(errors, "0"), errors > 0 ? "value-bad" : "value-good"],
          ["fatal_error", fatal ? tErr(fatal) : "无", fatal ? "value-bad" : ""]
        ]);
        if (fatal || errors > 0) {
          setTopStat("topLastRunState", "第" + asText(summary.run_id, "-") + "次（异常）", "warn");
        } else {
          setTopStat("topLastRunState", "第" + asText(summary.run_id, "-") + "次（成功）", "good");
        }
      }

      async function refreshRunSummary() {
        try {
          const data = await api("GET", "/api/status/run-once");
          renderRunSummary(data.summary || null);
          return true;
        } catch (err) {
          renderRows("runSummaryTable", [
            ["状态", "读取失败", "value-bad"],
            ["错误", tErr(err.message), "value-bad"]
          ]);
          setTopStat("topLastRunState", "读取失败", "bad");
          return false;
        }
      }

      async function clearLastRunError() {
        setActionState("runtimeState", "正在清空最近异常标记...", "loading");
        try {
          const data = await api("POST", "/api/actions/clear-last-run", {});
          await refreshRunSummary();
          if (data.cleared) {
            setMsg("最近同步异常已清空。", "success");
            setActionState("runtimeState", "最近异常已清空（" + nowClock() + "）", "success");
          } else {
            setMsg("最近同步摘要为空，无需清空。", "info");
            setActionState("runtimeState", "当前无异常可清空（" + nowClock() + "）", "success");
          }
          return true;
        } catch (err) {
          setActionState("runtimeState", "清空异常失败：" + tErr(err.message), "danger");
          setMsg("清空异常失败：" + tErr(err.message), "danger");
          return false;
        }
      }

      async function viewLastRunDetail() {
        activateTab("logs");
        document.getElementById("logN").value = "300";
        document.getElementById("logLevel").value = "WARNING";
        document.getElementById("logModule").value = "sync";
        setMsg("已切到日志巡检：level=WARNING，module=sync（可看到 remote_rename_failed 等异常详情）。", "info");
        return refreshLogs();
      }

      async function runOnce() {
        setActionState("runtimeState", "正在执行一次同步...", "loading");
        setRunBadge("running", "正在执行同步，请稍候");
        try {
          const data = await api("POST", "/api/actions/run-once", {});
          renderRunSummary(data || null);
          const hasErr = Boolean(data.fatal_error) || Number(data.errors || 0) > 0;
          if (hasErr) {
            setRunBadge("failed", "同步已完成，但有错误");
            setActionState("runtimeState", "本轮同步完成，但存在错误（" + nowClock() + "）", "warn");
            setMsg("同步完成，但存在错误，请查看 run summary。", "warn");
          } else {
            setRunBadge("success", "同步执行成功");
            setActionState("runtimeState", "本轮同步成功完成（" + nowClock() + "）", "success");
            setMsg("同步执行成功。", "success");
          }
          await Promise.all([refreshFeishu(), refreshTree(), refreshLogs(), refreshScheduler()]);
          return !hasErr;
        } catch (err) {
          setRunBadge("failed", "同步执行失败");
          setActionState("runtimeState", "同步执行失败：" + tErr(err.message), "danger");
          setMsg("执行同步失败：" + tErr(err.message), "danger");
          return false;
        }
      }

      async function restartService() {
        setActionState("runtimeState", "正在发送服务重启指令...", "loading");
        try {
          await api("POST", "/api/actions/restart", {});
          setMsg("重启命令已发送。", "success");
          const ok = await refreshService();
          await refreshScheduler();
          setActionState(
            "runtimeState",
            ok ? ("重启命令已发送，服务状态已刷新（" + nowClock() + "）") : "重启命令已发送，但状态刷新失败",
            ok ? "success" : "warn",
          );
          return ok;
        } catch (err) {
          setActionState("runtimeState", "重启服务失败：" + tErr(err.message), "danger");
          setMsg("重启服务失败：" + tErr(err.message), "danger");
          return false;
        }
      }

      async function refreshRuntime() {
        setActionState("runtimeState", "正在刷新运行状态...", "loading");
        const results = await Promise.all([refreshFeishu(), refreshService(), refreshScheduler(), refreshRunSummary()]);
        const ok = results.every((v) => !!v);
        setActionState(
          "runtimeState",
          ok ? ("运行状态已刷新（" + nowClock() + "）") : "运行状态已刷新，但存在异常项，请查看本区详情",
          ok ? "success" : "warn",
        );
        return ok;
      }

      async function refreshLogs() {
        setActionState("logsState", "正在读取日志...", "loading");
        const n = Number(document.getElementById("logN").value || "200");
        const level = document.getElementById("logLevel").value.trim();
        const module = document.getElementById("logModule").value.trim();
        const qs = new URLSearchParams();
        qs.set("n", String(Number.isFinite(n) ? Math.max(1, n) : 200));
        if (level) qs.set("level", level);
        if (module) qs.set("module", module);
        try {
          const data = await api("GET", "/api/logs?" + qs.toString());
          const tail = asText(data.tail, "");
          document.getElementById("logPane").textContent = tail;
          const lines = tail ? tail.split("\\n").filter((line) => line.trim() !== "").length : 0;
          setActionState("logsState", "日志已刷新（" + lines + " 行，" + nowClock() + "）", "success");
          return true;
        } catch (err) {
          document.getElementById("logPane").textContent = "读取日志失败：" + tErr(err.message);
          setActionState("logsState", "读取日志失败：" + tErr(err.message), "danger");
          setMsg("读取日志失败：" + tErr(err.message), "danger");
          return false;
        }
      }

      async function refreshAll() {
        setMsg("正在刷新全部面板...", "info");
        const configOk = await refreshConfigView();
        const treeOk = await refreshTree();
        const runtimeOk = await refreshRuntime();
        const logsOk = await refreshLogs();
        const ok = configOk && treeOk && runtimeOk && logsOk;
        setMsg(ok ? "全部面板已刷新。" : "刷新完成，但部分区域有异常，请查看各区提示。", ok ? "success" : "warn");
        return ok;
      }

      document.querySelectorAll(".tab").forEach((tab) => {
        tab.addEventListener("click", () => activateTab(tab.dataset.tab));
      });
      bindButtonAction("btnRefreshAllTop", "刷新中...", refreshAll);
      document.getElementById("btnGoRuntime").addEventListener("click", () => activateTab("runtime"));

      bindButtonAction("btnSaveConfig", "保存中...", saveConfig);
      bindButtonAction("btnAuthUrl", "生成中...", genAuthUrl);
      bindButtonAction("btnExchangeCode", "交换中...", exchangeCode);
      bindButtonAction("btnRefreshToken", "刷新中...", refreshToken);
      document.getElementById("fPollIntervalPreset").addEventListener("change", (event) => {
        const value = asText(event.target.value, "");
        if (value !== "") {
          document.getElementById("fPollIntervalSec").value = value;
          setActionState("configState", "已应用间隔预设，请点击“保存基础配置”生效。", "loading");
        }
      });

      bindButtonAction("btnRefreshTree", "刷新中...", refreshTree);
      bindButtonAction("btnExpandAllTree", "展开中...", async () => expandAllTree());
      bindButtonAction("btnCollapseAllTree", "折叠中...", async () => collapseAllTree());
      bindButtonAction("btnRunOnce", "执行中...", runOnce);
      bindButtonAction("btnRestartService", "重启中...", restartService);
      bindButtonAction("btnRefreshRuntime", "刷新中...", refreshRuntime);
      bindButtonAction("btnViewLastRunDetail", "跳转中...", viewLastRunDetail);
      bindButtonAction("btnClearLastRunError", "清空中...", clearLastRunError);
      bindButtonAction("btnRefreshLogs", "刷新中...", refreshLogs);

      if (OUT_OF_SCOPE) setMsg("检测到 local_root 越界，运行时会自动锁定。", "warn");
      ensureAutoSyncTicker();
      refreshAll();
      window.setInterval(() => {
        refreshScheduler().catch(() => {});
      }, 15000);
    </script>
  </body>
</html>
"""

    return (
        page.replace("__SCOPE_BANNER__", scope_banner)
        .replace("__FIXED_LOCAL_ROOT__", escape(_as_text(FIXED_LOCAL_ROOT)))
        .replace("__AUTH_APP_ID__", escape(_as_text(cfg.auth.app_id)))
        .replace("__AUTH_APP_SECRET__", escape(_as_text(cfg.auth.app_secret)))
        .replace("__AUTH_USER_TOKEN_FILE__", escape(_as_text(cfg.auth.user_token_file)))
        .replace("__WEB_BIND_HOST__", escape(_as_text(cfg.web_bind_host)))
        .replace("__WEB_PORT__", escape(_as_text(cfg.web_port)))
        .replace("__OUT_OF_SCOPE__", "true" if out_of_scope else "false")
        .replace("__LAST_RUN_PATH__", escape(str(LAST_RUN_ONCE_PATH)))
    )
