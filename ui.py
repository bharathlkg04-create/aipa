from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["ui"])

_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>AI'PA Dashboard</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      font-family: 'Segoe UI', system-ui, sans-serif;
      background: #0f1117;
      color: #e2e8f0;
      min-height: 100vh;
      padding: 32px 16px;
    }

    .container { max-width: 860px; margin: 0 auto; }

    /* ── Header ── */
    .header {
      display: flex;
      align-items: center;
      gap: 14px;
      margin-bottom: 36px;
    }
    .logo {
      width: 48px; height: 48px;
      background: linear-gradient(135deg, #6366f1, #8b5cf6);
      border-radius: 14px;
      display: flex; align-items: center; justify-content: center;
      font-size: 24px;
    }
    .header h1 { font-size: 28px; font-weight: 700; letter-spacing: -0.5px; }
    .header p  { font-size: 13px; color: #64748b; margin-top: 2px; }

    /* ── Grid ── */
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 16px;
      margin-bottom: 24px;
    }

    /* ── Card ── */
    .card {
      background: #1e2130;
      border: 1px solid #2d3148;
      border-radius: 14px;
      padding: 20px 22px;
    }
    .card-label {
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: #64748b;
      margin-bottom: 10px;
    }
    .card-value {
      font-size: 22px;
      font-weight: 700;
      color: #f1f5f9;
    }
    .card-sub { font-size: 12px; color: #475569; margin-top: 4px; }

    /* ── Status badge ── */
    .badge {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 4px 10px;
      border-radius: 20px;
      font-size: 12px;
      font-weight: 600;
    }
    .badge-green  { background: #14532d33; color: #4ade80; border: 1px solid #166534; }
    .badge-red    { background: #7f1d1d33; color: #f87171; border: 1px solid #991b1b; }
    .badge-yellow { background: #78350f33; color: #fbbf24; border: 1px solid #92400e; }
    .dot { width: 7px; height: 7px; border-radius: 50%; background: currentColor; }

    /* ── Section title ── */
    .section-title {
      font-size: 13px;
      font-weight: 600;
      color: #94a3b8;
      margin: 28px 0 12px;
      text-transform: uppercase;
      letter-spacing: 0.06em;
    }

    /* ── Webhook box ── */
    .webhook-box {
      background: #1e2130;
      border: 1px solid #2d3148;
      border-radius: 14px;
      padding: 18px 22px;
      margin-bottom: 16px;
    }
    .webhook-url {
      font-family: 'Cascadia Code', 'Fira Code', monospace;
      font-size: 13px;
      color: #a78bfa;
      word-break: break-all;
      background: #0f1117;
      padding: 10px 14px;
      border-radius: 8px;
      margin: 10px 0;
      border: 1px solid #2d3148;
    }
    .copy-btn {
      background: #6366f1;
      color: white;
      border: none;
      padding: 7px 16px;
      border-radius: 8px;
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
      transition: background 0.15s;
    }
    .copy-btn:hover { background: #4f46e5; }

    /* ── Links ── */
    .links { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 24px; }
    .link-btn {
      display: inline-flex;
      align-items: center;
      gap: 7px;
      padding: 9px 18px;
      border-radius: 10px;
      font-size: 13px;
      font-weight: 600;
      text-decoration: none;
      transition: opacity 0.15s;
    }
    .link-btn:hover { opacity: 0.85; }
    .link-primary   { background: #6366f1; color: white; }
    .link-secondary { background: #1e2130; color: #94a3b8; border: 1px solid #2d3148; }

    /* ── Simulate ── */
    .sim-form { display: flex; gap: 10px; flex-wrap: wrap; }
    .sim-form input, .sim-form select {
      flex: 1;
      min-width: 160px;
      background: #0f1117;
      border: 1px solid #2d3148;
      border-radius: 8px;
      padding: 9px 14px;
      color: #e2e8f0;
      font-size: 13px;
      outline: none;
    }
    .sim-form input:focus, .sim-form select:focus { border-color: #6366f1; }
    .sim-btn {
      background: #6366f1;
      color: white;
      border: none;
      padding: 9px 20px;
      border-radius: 8px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      transition: background 0.15s;
    }
    .sim-btn:hover { background: #4f46e5; }
    .sim-result {
      margin-top: 12px;
      background: #0f1117;
      border: 1px solid #2d3148;
      border-radius: 8px;
      padding: 12px 14px;
      font-size: 13px;
      font-family: monospace;
      color: #94a3b8;
      min-height: 46px;
      white-space: pre-wrap;
      word-break: break-all;
    }

    /* ── Footer ── */
    .footer {
      margin-top: 40px;
      text-align: center;
      font-size: 12px;
      color: #334155;
    }
  </style>
</head>
<body>
<div class="container">

  <!-- Header -->
  <div class="header">
    <div class="logo">🤖</div>
    <div>
      <h1>AI'PA Dashboard</h1>
      <p>Multi-tenant AI Agent Platform — BYOK</p>
    </div>
  </div>

  <!-- Status cards -->
  <div class="grid">
    <div class="card">
      <div class="card-label">Server Status</div>
      <div id="server-status"><span class="badge badge-yellow"><span class="dot"></span>Checking…</span></div>
      <div class="card-sub" id="server-env"></div>
    </div>
    <div class="card">
      <div class="card-label">Database</div>
      <div id="db-status"><span class="badge badge-yellow"><span class="dot"></span>Checking…</span></div>
      <div class="card-sub">Supabase (asyncpg)</div>
    </div>
    <div class="card">
      <div class="card-label">Base URL</div>
      <div class="card-value" style="font-size:14px; word-break:break-all;" id="base-url">—</div>
      <div class="card-sub">Current origin</div>
    </div>
  </div>

  <!-- Quick links -->
  <p class="section-title">Quick Links</p>
  <div class="links">
    <a href="/docs" class="link-btn link-primary" target="_blank">📖 Swagger UI</a>
    <a href="/health" class="link-btn link-secondary" target="_blank">❤️ Health JSON</a>
    <a href="/health/live" class="link-btn link-secondary" target="_blank">⚡ Liveness</a>
  </div>

  <!-- Webhook URL helper -->
  <p class="section-title">Telegram Webhook URL</p>
  <div class="webhook-box">
    <div class="card-sub">Paste your bot token below to generate the webhook URL to register with Telegram.</div>
    <div style="display:flex; gap:10px; margin-top:12px; flex-wrap:wrap;">
      <input id="bot-token-input" placeholder="Bot token (e.g. 7123456789:AAF...)"
             style="flex:1; min-width:220px; background:#0f1117; border:1px solid #2d3148;
                    border-radius:8px; padding:9px 14px; color:#e2e8f0; font-size:13px; outline:none;" />
      <button class="copy-btn" onclick="generateWebhook()">Generate</button>
    </div>
    <div class="webhook-url" id="webhook-url">— enter bot token above —</div>
    <div style="display:flex; align-items:center; gap:10px; flex-wrap:wrap;">
      <button class="copy-btn" onclick="copyWebhook()">📋 Copy URL</button>
      <button class="copy-btn" onclick="registerWebhook()" style="background:#059669;">⚡ Register Webhook</button>
      <span id="copy-msg" style="font-size:12px; color:#4ade80; opacity:0; transition:opacity 0.3s;">Copied!</span>
    </div>
    <div id="register-result" style="font-size:12px; margin-top:10px; font-family:monospace; min-height:18px;"></div>
  </div>

  <!-- Simulate health ping -->
  <p class="section-title">API Tester</p>
  <div class="card">
    <div class="card-label">Send a request to any endpoint</div>
    <div class="sim-form" style="margin-top:10px;">
      <select id="sim-method">
        <option>GET</option>
        <option>POST</option>
      </select>
      <input id="sim-path" value="/health" placeholder="/health" />
      <button class="sim-btn" onclick="sendRequest()">Send</button>
    </div>
    <div class="sim-result" id="sim-result">Response will appear here…</div>
  </div>

  <div class="footer">AI'PA · FastAPI + Supabase + LiteLLM · Built for small businesses</div>
</div>

<script>
  const origin = window.location.origin;
  document.getElementById('base-url').textContent = origin;

  // ── Health check ──
  async function checkHealth() {
    try {
      const r = await fetch('/health');
      const d = await r.json();
      document.getElementById('server-status').innerHTML =
        d.status === 'healthy'
          ? '<span class="badge badge-green"><span class="dot"></span>Healthy</span>'
          : '<span class="badge badge-red"><span class="dot"></span>Degraded</span>';
      document.getElementById('db-status').innerHTML =
        d.db === 'ok'
          ? '<span class="badge badge-green"><span class="dot"></span>Connected</span>'
          : '<span class="badge badge-red"><span class="dot"></span>Unreachable</span>';
      document.getElementById('server-env').textContent = 'env: ' + (d.environment || '—');
    } catch {
      document.getElementById('server-status').innerHTML =
        '<span class="badge badge-red"><span class="dot"></span>Offline</span>';
      document.getElementById('db-status').innerHTML =
        '<span class="badge badge-red"><span class="dot"></span>Unknown</span>';
    }
  }
  checkHealth();
  setInterval(checkHealth, 10000);

  // ── Webhook generator ──
  function generateWebhook() {
    const token = document.getElementById('bot-token-input').value.trim();
    if (!token) { document.getElementById('webhook-url').textContent = '— enter bot token above —'; return; }
    document.getElementById('webhook-url').textContent = origin + '/webhook/telegram/' + token;
  }

  function copyWebhook() {
    const url = document.getElementById('webhook-url').textContent;
    if (url.startsWith('—')) return;
    navigator.clipboard.writeText(url);
    const msg = document.getElementById('copy-msg');
    msg.style.opacity = '1';
    setTimeout(() => msg.style.opacity = '0', 2000);
  }

  async function registerWebhook() {
    const token = document.getElementById('bot-token-input').value.trim();
    const el = document.getElementById('register-result');
    if (!token) { el.style.color = '#fbbf24'; el.textContent = 'Enter your bot token first.'; return; }
    el.style.color = '#94a3b8';
    el.textContent = 'Registering…';
    try {
      const r = await fetch(origin + '/webhook/telegram/' + token + '/setup-webhook', { method: 'POST' });
      const d = await r.json();
      if (d.ok) {
        el.style.color = '#4ade80';
        el.textContent = '✓ Registered: ' + d.webhook_url;
      } else {
        el.style.color = '#f87171';
        el.textContent = 'Error: ' + (d.detail || JSON.stringify(d));
      }
    } catch (e) {
      el.style.color = '#f87171';
      el.textContent = 'Error: ' + e.message;
    }
  }

  // ── API tester ──
  async function sendRequest() {
    const method = document.getElementById('sim-method').value;
    const path   = document.getElementById('sim-path').value.trim() || '/health';
    const el     = document.getElementById('sim-result');
    el.textContent = 'Loading…';
    try {
      const r = await fetch(origin + path, { method });
      const text = await r.text();
      let display;
      try { display = JSON.stringify(JSON.parse(text), null, 2); }
      catch { display = text; }
      el.textContent = 'HTTP ' + r.status + '\\n\\n' + display;
    } catch (e) {
      el.textContent = 'Error: ' + e.message;
    }
  }
</script>
</body>
</html>
"""


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def dashboard() -> HTMLResponse:
    return HTMLResponse(content=_HTML)
