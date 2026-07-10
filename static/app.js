/* AI'PA dashboard — vanilla JS, talks to the FastAPI backend. */

"use strict";

// ── Auth state (localStorage) ────────────────────────────────────────────────
const AUTH_KEY = "aipa_auth";

function getAuth() {
  try { return JSON.parse(localStorage.getItem(AUTH_KEY)) || null; }
  catch { return null; }
}
function setAuth(a) { localStorage.setItem(AUTH_KEY, JSON.stringify(a)); }
function clearAuth() { localStorage.removeItem(AUTH_KEY); }

// Email/password account session ("acct_…" bearer token)
const ACCT_KEY = "aipa_acct";
function getAcct() {
  try { return JSON.parse(localStorage.getItem(ACCT_KEY)) || null; }
  catch { return null; }
}
function setAcct(a) { localStorage.setItem(ACCT_KEY, JSON.stringify(a)); }
function clearAcct() { localStorage.removeItem(ACCT_KEY); }

function $(id) { return document.getElementById(id); }

function msg(id, kind, text) {
  const el = $(id);
  el.className = "form-msg " + (kind || "");
  el.textContent = text || "";
}

// ── Google Sign-In (Google Identity Services) ────────────────────────────────
// The official button yields a one-time ID token; POST /api/auth/google
// verifies it and returns the business's owner session, which we store like
// a normal login. The Google token is only kept in memory for the onboarding
// calls (setup / link) made right after signing in.
let _googleReady = false;   // GIS script loaded & initialized
let _googleCred = null;     // ID token of the current sign-in, memory only

function loadGoogleSignIn(clientId) {
  return new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = "https://accounts.google.com/gsi/client";
    s.async = true;
    s.onload = () => {
      try {
        google.accounts.id.initialize({
          client_id: clientId,
          callback: onGoogleCredential,
        });
        _googleReady = true;
        resolve();
      } catch (e) { reject(e); }
    };
    s.onerror = () => reject(new Error("Could not load Google sign-in"));
    document.head.appendChild(s);
  });
}

async function onGoogleCredential(response) {
  _googleCred = response.credential;
  msg("g-msg", "warn", "Checking your account…");
  try {
    const d = await api("/api/auth/google", {
      method: "POST",
      body: JSON.stringify({ credential: _googleCred }),
    });
    if (d.linked) {
      setAuth({
        businessId: d.business.id,
        ownerToken: d.business.owner_token,
        businessName: d.business.name,
      });
      showAppView();
    } else {
      showOnboarding(d.email || "");
    }
  } catch (e) {
    msg("g-msg", "err", "Sign-in failed: " + e.message);
  }
}

// Single source of truth for request credentials: the owner token, plus the
// one-time Google credential during onboarding. EVERY authenticated request —
// including raw fetch() calls for binary responses like the WhatsApp QR —
// must use this, never build auth headers by hand.
async function authHeaders() {
  const headers = {};
  const acct = getAcct();
  if (_googleCred) headers["Authorization"] = "Bearer " + _googleCred;
  else if (acct && acct.token) headers["Authorization"] = "Bearer " + acct.token;
  const auth = getAuth();
  if (auth && auth.ownerToken) headers["X-Owner-Token"] = auth.ownerToken;
  return headers;
}

async function api(path, options = {}) {
  const headers = {
    "Content-Type": "application/json",
    ...(await authHeaders()),
    ...(options.headers || {}),
  };

  // Free-tier hosting throws transient 502/503s (cold starts, restarts) —
  // retry idempotent GETs a couple of times before giving up.
  const retriable = !options.method || options.method === "GET";
  const attempts = retriable ? 3 : 1;
  let lastErr = null;
  for (let i = 0; i < attempts; i++) {
    if (i > 0) await new Promise((res) => setTimeout(res, 1500 * i));
    let r;
    try {
      r = await fetch(path, { ...options, headers });
    } catch (e) {
      lastErr = new Error("Network error — server may be waking up");
      continue;
    }
    let data = null;
    try { data = await r.json(); } catch { /* non-JSON body */ }
    if (r.ok) return data;
    lastErr = new Error((data && data.detail) || "HTTP " + r.status);
    if (r.status !== 502 && r.status !== 503 && r.status !== 504) throw lastErr;
  }
  throw lastErr;
}

// ── Model options (shared by setup + personality) ────────────────────────────
const MODELS = [
  ["openai/gpt-4o-mini", "OpenAI — gpt-4o-mini (fast & cheap)"],
  ["openai/gpt-4o", "OpenAI — gpt-4o (powerful)"],
  ["anthropic/claude-haiku-4-5-20251001", "Anthropic — Claude Haiku (fast)"],
  ["anthropic/claude-sonnet-4-6", "Anthropic — Claude Sonnet (powerful)"],
  ["google/gemini-1.5-flash", "Google — Gemini 1.5 Flash"],
  ["google/gemini-1.5-pro", "Google — Gemini 1.5 Pro"],
  ["groq/llama-3.1-8b-instant", "Groq — Llama 3.1 8B (free tier)"],
  ["groq/llama-3.3-70b-versatile", "Groq — Llama 3.3 70B"],
  ["custom", "Custom model string…"],
];

function fillModelSelect(selectId, customId) {
  const sel = $(selectId);
  sel.innerHTML = "";
  MODELS.forEach(([v, label]) => {
    const o = document.createElement("option");
    o.value = v; o.textContent = label;
    sel.appendChild(o);
  });
  sel.onchange = () => { $(customId).hidden = sel.value !== "custom"; };
}

function readModel(selectId, customId) {
  const v = $(selectId).value;
  return v === "custom" ? $(customId).value.trim() : v;
}

function setModel(selectId, customId, model) {
  const sel = $(selectId);
  if (MODELS.some(([v]) => v === model)) {
    sel.value = model;
    $(customId).hidden = true;
  } else {
    sel.value = "custom";
    $(customId).value = model;
    $(customId).hidden = false;
  }
}

// ── Views & tabs ─────────────────────────────────────────────────────────────
let _googleOn = false; // GIS configured & loaded — show the Google button

function _authCards(visible) {
  ["card-google", "card-create", "card-login", "card-link",
   "card-signup", "card-signin"].forEach((id) => {
    $(id).hidden = !visible.includes(id);
  });
}

function togglePw(inputId, btn) {
  const el = $(inputId);
  el.type = el.type === "password" ? "text" : "password";
  btn.style.opacity = el.type === "password" ? "" : "1";
}

function _renderGoogleBtn() {
  if (!_googleOn) return;
  // Real GIS button sits invisibly over our own "Sign in with Google" —
  // full visual control, so Google can never swap in "Continue as …".
  $("g-signin").innerHTML = "";
  google.accounts.id.renderButton($("g-signin"), {
    theme: "outline", size: "large", shape: "rect", width: 400, text: "signin_with",
  });
}

function _showAuth(sub, cards, withGoogle) {
  $("view-auth").hidden = false;
  $("view-app").hidden = true;
  $("auth-user-bar").hidden = true;
  $("auth-sub").textContent = sub;
  if (withGoogle && _googleOn) cards = cards.concat(["card-google"]);
  _authCards(cards);
  if (withGoogle) _renderGoogleBtn();
}

function showSignUp() { _showAuth("Create your account", ["card-signup"], true); }
function showSignIn() { _showAuth("Sign in to your account", ["card-signin"], true); }
function showTokenLogin() { _showAuth("Sign in with owner token", ["card-login"], false); }

// Legacy alias (older code paths call this on sign-out / fallbacks)
function showAuthView() { showSignUp(); }

function showOnboarding(email) {
  // Signed in with Google but no business yet: create one or link one.
  $("view-auth").hidden = false;
  $("view-app").hidden = true;
  $("auth-sub").textContent = "Set up your assistant";
  const bar = $("auth-user-bar");
  bar.hidden = false;
  bar.textContent = "✓ Signed in" + (email ? " as " + email : "") +
    " — now create your assistant (or link an existing one).";
  _authCards(["card-create", "card-link"]);
  // If this browser has a legacy session, prefill the link form: migrating
  // becomes a single click.
  const legacy = getAuth();
  if (legacy && legacy.ownerToken) {
    $("lk-business").value = legacy.businessId || "";
    $("lk-owner").value = legacy.ownerToken;
  }
}

function showAppView() {
  $("view-auth").hidden = true;
  $("view-app").hidden = false;
  $("biz-name").textContent = (getAuth() || {}).businessName || "";
  switchTab("skills");
  loadAccount();
}

const TAB_LOADERS = {
  skills: loadMySkills,
  store: () => { loadStoreMeta(); loadStore(true); },
  channels: loadChannels,
  keys: renderKeys,
  personality: renderPersonality,
  conversations: loadConversations,
  logs: loadLogs,
};

const PANELS = ["skills", "store", "channels", "keys", "personality", "conversations", "logs"];

const PAGE_TITLES = {
  skills: "Skills",
  store: "Skill Store",
  channels: "Channels",
  keys: "API Keys",
  personality: "Personality",
  conversations: "Conversations",
  logs: "Logs",
};

function switchTab(name) {
  document.querySelectorAll(".tab").forEach((t) =>
    t.classList.toggle("active", t.dataset.tab === name)
  );
  PANELS.forEach((p) => {
    $("panel-" + p).hidden = p !== name;
  });
  $("page-title").textContent = PAGE_TITLES[name] || "";
  if (name !== "channels") waStopPolling();
  closeSidebar(); // mobile: navigating closes the drawer
  (TAB_LOADERS[name] || (() => {}))();
}

document.addEventListener("click", (e) => {
  const tab = e.target.closest(".tab");
  if (tab) switchTab(tab.dataset.tab);
});

// ── Sidebar (collapsible group + mobile drawer) ──────────────────────────────
function toggleNavGroup(e) {
  const head = e.currentTarget;
  head.classList.toggle("open");
  $("nav-group-agent").classList.toggle("collapsed", !head.classList.contains("open"));
}

function openSidebar() {
  $("sidebar").classList.add("open");
  $("sidebar-scrim").classList.add("show");
}

function closeSidebar() {
  $("sidebar").classList.remove("open");
  $("sidebar-scrim").classList.remove("show");
}

function signOut() {
  waStopPolling();
  clearAuth();
  clearAcct();
  _account = null;
  _googleCred = null;
  if (_googleReady) {
    try { google.accounts.id.disableAutoSelect(); } catch (e) { /* non-fatal */ }
  }
  location.reload(); // clean re-boot of the auth view
}

// ── Bot token auto-recognition ───────────────────────────────────────────────
let _botVerifyTimer = null;
let _verifiedBot = null;

function onBotTokenInput() {
  clearTimeout(_botVerifyTimer);
  _verifiedBot = null;
  const token = $("su-token").value.trim();
  const hint = $("su-bot-hint");
  if (token.length < 20) { hint.textContent = ""; return; }
  hint.className = "form-msg warn";
  hint.textContent = "Checking token with Telegram…";
  _botVerifyTimer = setTimeout(() => verifyBotToken(token), 600);
}

async function verifyBotToken(token) {
  const hint = $("su-bot-hint");
  try {
    const d = await api("/api/telegram/verify", {
      method: "POST",
      body: JSON.stringify({ bot_token: token }),
    });
    if ($("su-token").value.trim() !== token) return; // user kept typing
    if (d.ok && d.bot) {
      _verifiedBot = d.bot;
      hint.className = "form-msg ok";
      hint.textContent = "✓ Recognised: " + (d.bot.name || "bot") +
        (d.bot.username ? " (@" + d.bot.username + ")" : "");
      const nameField = $("su-name");
      if (!nameField.value.trim() && d.bot.name) nameField.value = d.bot.name;
    } else {
      hint.className = "form-msg err";
      hint.textContent = "✗ " + (d.detail || "Telegram does not recognise this token.");
    }
  } catch (e) {
    hint.className = "form-msg warn";
    hint.textContent = "Could not verify right now (" + e.message + ") — you can still continue.";
  }
}

// ── Setup & login ────────────────────────────────────────────────────────────
async function doSetup() {
  const name = $("su-name").value.trim() || "My Business";
  const token = $("su-token").value.trim();
  const apikey = $("su-apikey").value.trim();
  const model = readModel("su-model", "su-model-custom");
  if (!token) return msg("su-msg", "err", "Telegram bot token is required.");
  if (!apikey) return msg("su-msg", "err", "LLM API key is required.");
  if (!model) return msg("su-msg", "err", "Model is required.");

  const btn = $("su-btn");
  btn.disabled = true;
  msg("su-msg", "warn", "Connecting… (a sleeping free-tier server can take up to 60s)");
  try {
    const d = await api("/api/setup", {
      method: "POST",
      body: JSON.stringify({ bot_token: token, api_key: apikey, model, business_name: name }),
    });
    setAuth({ businessId: d.business_id, ownerToken: d.owner_token, businessName: name });
    if (d.linked) {
      // Business is bound to the signed-in Google account — Google login from now on.
      msg("su-msg", "ok", "✓ Connected! Your business is linked to your Google account.");
      setTimeout(showAppView, 900);
    } else {
      msg("su-msg", "ok", "✓ Connected! Owner token saved in this browser:\n" + d.owner_token +
          "\nCopy it somewhere safe — it is your password.");
      setTimeout(showAppView, 1600);
    }
  } catch (e) {
    msg("su-msg", "err", "Setup failed: " + e.message);
  } finally {
    btn.disabled = false;
  }
}

async function doSignup() {
  const name = $("sg-name").value.trim();
  const email = $("sg-email").value.trim();
  const password = $("sg-password").value;
  if (!name || !email) return msg("sg-msg", "err", "Full name and email are required.");
  if (password.length < 8) return msg("sg-msg", "err", "Password must be at least 8 characters.");

  const btn = $("sg-btn");
  btn.disabled = true;
  msg("sg-msg", "warn", "Creating your account…");
  try {
    const d = await api("/api/auth/signup", {
      method: "POST",
      body: JSON.stringify({ full_name: name, email: email, password: password }),
    });
    setAcct({ token: d.account_token, name: d.account.name, email: d.account.email });
    showOnboarding(d.account.email);
  } catch (e) {
    msg("sg-msg", "err", e.message);
  } finally {
    btn.disabled = false;
  }
}

async function doEmailLogin() {
  const email = $("si-email").value.trim();
  const password = $("si-password").value;
  if (!email || !password) return msg("si-msg", "err", "Both fields are required.");

  const btn = $("si-btn");
  btn.disabled = true;
  msg("si-msg", "warn", "Signing in…");
  try {
    const d = await api("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email: email, password: password }),
    });
    setAcct({ token: d.account_token, name: d.account.name, email: d.account.email });
    if (d.business) {
      setAuth({
        businessId: d.business.id,
        ownerToken: d.business.owner_token,
        businessName: d.business.name,
      });
      showAppView();
    } else {
      showOnboarding(d.account.email);
    }
  } catch (e) {
    msg("si-msg", "err", e.message);
  } finally {
    btn.disabled = false;
  }
}

async function doLogin() {
  const businessId = $("li-business").value.trim();
  const ownerToken = $("li-owner").value.trim();
  if (!businessId || !ownerToken) return msg("li-msg", "err", "Both fields are required.");

  const btn = $("li-btn");
  btn.disabled = true;
  msg("li-msg", "warn", "Signing in…");
  try {
    const r = await fetch("/api/account?business_id=" + encodeURIComponent(businessId), {
      headers: { "X-Owner-Token": ownerToken },
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || "HTTP " + r.status);
    setAuth({ businessId, ownerToken, businessName: d.business.name });
    _account = d;
    msg("li-msg", "ok", "✓ Welcome back, " + d.business.name);
    setTimeout(showAppView, 500);
  } catch (e) {
    msg("li-msg", "err", "Sign-in failed: " + e.message);
  } finally {
    btn.disabled = false;
  }
}

async function doLink() {
  const businessId = $("lk-business").value.trim();
  const ownerToken = $("lk-owner").value.trim();
  if (!businessId || !ownerToken) return msg("lk-msg", "err", "Both fields are required.");

  const btn = $("lk-btn");
  btn.disabled = true;
  msg("lk-msg", "warn", "Linking…");
  try {
    const d = await api("/api/auth/link", {
      method: "POST",
      body: JSON.stringify({ business_id: businessId, owner_token: ownerToken }),
    });
    setAuth({ businessId: d.business.id, ownerToken, businessName: d.business.name });
    msg("lk-msg", "ok", "✓ Linked " + d.business.name + " — next time, Google sign-in is enough.");
    setTimeout(showAppView, 900);
  } catch (e) {
    msg("lk-msg", "err", "Link failed: " + e.message);
  } finally {
    btn.disabled = false;
  }
}

// ── Account data (config, key, channels) ─────────────────────────────────────
let _account = null;

async function loadAccount(force = false) {
  if (_account && !force) return _account;
  const auth = getAuth();
  _account = await api("/api/account?business_id=" + encodeURIComponent(auth.businessId));
  $("biz-name").textContent = _account.business.name;
  return _account;
}

// ── Skills tab (enabled skills, grouped by category) ─────────────────────────
async function loadMySkills() {
  const auth = getAuth();
  const wrap = $("skills-groups");
  wrap.innerHTML = '<div class="empty-state">Loading…</div>';
  $("skills-empty").hidden = true;
  try {
    const d = await api(
      "/api/skills?business_id=" + encodeURIComponent(auth.businessId) +
      "&enabled_only=true&limit=100"
    );
    const skills = d.skills || [];
    $("skills-count").textContent = d.enabled_count + " enabled";
    wrap.innerHTML = "";
    if (!skills.length) {
      $("skills-empty").hidden = false;
      return;
    }
    const groups = {};
    skills.forEach((s) => {
      const cat = s.category || "general";
      (groups[cat] = groups[cat] || []).push(s);
    });
    Object.keys(groups).sort().forEach((cat) => {
      const title = document.createElement("div");
      title.className = "group-title";
      title.textContent = cat.replace(/-/g, " ");
      wrap.appendChild(title);
      const grid = document.createElement("div");
      grid.className = "skill-grid";
      groups[cat].forEach((s) => grid.appendChild(renderSkillCard(s)));
      wrap.appendChild(grid);
    });
  } catch (e) {
    wrap.innerHTML = '<div class="empty-state">Error: ' + e.message + "</div>";
  }
}

function renderSkillCard(s) {
  const card = document.createElement("div");
  card.className = "skill-card on";

  const info = document.createElement("div");
  const name = document.createElement("div");
  name.className = "sk-name";
  name.textContent = s.name;
  const chip = document.createElement("span");
  chip.className = "on-chip";
  chip.textContent = "ON";
  name.appendChild(chip);
  const desc = document.createElement("div");
  desc.className = "sk-desc";
  desc.textContent = s.description || "";
  info.appendChild(name);
  info.appendChild(desc);

  const toggle = document.createElement("button");
  toggle.className = "toggle on";
  toggle.onclick = async () => {
    toggle.disabled = true;
    try {
      await toggleSkill(s.id, false);
      card.remove();
      loadMySkills();
    } catch (e) {
      toggle.disabled = false;
      alert("Toggle failed: " + e.message);
    }
  };

  card.appendChild(info);
  card.appendChild(toggle);
  return card;
}

async function toggleSkill(skillId, isEnabled) {
  const auth = getAuth();
  return api("/api/skills/" + skillId + "/toggle", {
    method: "PUT",
    body: JSON.stringify({ business_id: auth.businessId, is_enabled: isEnabled }),
  });
}

// ── Skill Store tab ──────────────────────────────────────────────────────────
let _stCategory = null;
let _stOffset = 0;
let _stTimer = null;
let _stMetaLoaded = false;
const ST_PAGE = 30;

async function loadStoreMeta() {
  if (_stMetaLoaded) return;
  try {
    const d = await api("/api/skills/meta");
    _stMetaLoaded = true;
    $("store-total").textContent = d.total + " skills";
    const sel = $("st-industry");
    (d.industries || []).forEach((i) => {
      if (i.industry === "generic") return;
      const o = document.createElement("option");
      o.value = i.industry;
      o.textContent = i.industry.replace(/-/g, " ") + " (" + i.n + ")";
      sel.appendChild(o);
    });
    const chips = $("st-chips");
    chips.innerHTML = "";
    chips.appendChild(makeChip("All", null, true));
    (d.categories || []).forEach((c) => chips.appendChild(makeChip(c.category, c.category, false)));
  } catch { /* retried on next tab open */ }
}

function makeChip(label, value, active) {
  const el = document.createElement("button");
  el.className = "chip" + (active ? " active" : "");
  el.textContent = label;
  el.onclick = () => {
    _stCategory = value;
    document.querySelectorAll("#st-chips .chip").forEach((c) => c.classList.remove("active"));
    el.classList.add("active");
    loadStore(true);
  };
  return el;
}

function onStoreSearch() {
  clearTimeout(_stTimer);
  _stTimer = setTimeout(() => loadStore(true), 350);
}

async function loadStore(reset) {
  const auth = getAuth();
  if (reset) _stOffset = 0;
  const params = new URLSearchParams({
    business_id: auth.businessId, limit: ST_PAGE, offset: _stOffset,
  });
  const industry = $("st-industry").value;
  if (industry) params.set("industry", industry);
  if (_stCategory) params.set("category", _stCategory);
  const q = $("st-search").value.trim();
  if (q) params.set("q", q);

  const list = $("st-list");
  if (reset) list.innerHTML = '<div class="skill-row">Loading…</div>';
  try {
    const d = await api("/api/skills?" + params);
    if (reset) list.innerHTML = "";
    const skills = d.skills || [];
    if (reset && !skills.length) {
      list.innerHTML = '<div class="skill-row">No skills match these filters.</div>';
    }
    skills.forEach((s) => list.appendChild(renderStoreRow(s)));
    _stOffset += skills.length;
    $("st-more").hidden = skills.length !== ST_PAGE;
    msg("st-msg", "ok", d.enabled_count + " skills enabled for your business");
  } catch (e) {
    list.innerHTML = '<div class="skill-row">Error: ' + e.message + "</div>";
  }
}

function renderStoreRow(s) {
  const row = document.createElement("div");
  row.className = "skill-row";

  const info = document.createElement("div");
  const name = document.createElement("div");
  name.className = "sk-name";
  name.textContent = s.name;
  if (s.is_enabled) {
    const chip = document.createElement("span");
    chip.className = "on-chip";
    chip.textContent = "ON";
    name.appendChild(chip);
  }
  const desc = document.createElement("div");
  desc.className = "sk-desc";
  desc.textContent = s.description || "";
  const tags = document.createElement("div");
  tags.className = "sk-tags";
  [s.industry, s.category].forEach((t) => {
    if (!t) return;
    const tag = document.createElement("span");
    tag.className = "sk-tag";
    tag.textContent = t.replace(/-/g, " ");
    tags.appendChild(tag);
  });
  info.appendChild(name); info.appendChild(desc); info.appendChild(tags);

  const toggle = document.createElement("button");
  toggle.className = "toggle" + (s.is_enabled ? " on" : "");
  toggle.onclick = async () => {
    const turnOn = !toggle.classList.contains("on");
    toggle.disabled = true;
    try {
      const d = await toggleSkill(s.id, turnOn);
      toggle.classList.toggle("on", turnOn);
      const chip = name.querySelector(".on-chip");
      if (turnOn && !chip) {
        const c = document.createElement("span");
        c.className = "on-chip"; c.textContent = "ON";
        name.appendChild(c);
      } else if (!turnOn && chip) chip.remove();
      msg("st-msg", "ok", d.enabled_count + " skills enabled for your business");
    } catch (e) {
      msg("st-msg", "err", "Toggle failed: " + e.message);
    } finally {
      toggle.disabled = false;
    }
  };

  row.appendChild(info);
  row.appendChild(toggle);
  return row;
}

async function enablePack() {
  const auth = getAuth();
  const industry = $("st-industry").value;
  if (!industry) return msg("st-msg", "warn", "Pick your industry first, then enable its starter pack.");
  msg("st-msg", "warn", "Enabling starter pack…");
  try {
    const d = await api("/api/skills/enable-pack", {
      method: "POST",
      body: JSON.stringify({ business_id: auth.businessId, industry }),
    });
    msg("st-msg", "ok", "✓ Starter pack enabled (" + d.skills_enabled + " skills). Total: " + d.enabled_count);
    loadStore(true);
  } catch (e) {
    msg("st-msg", "err", "Error: " + e.message);
  }
}

// ── Channels tab ─────────────────────────────────────────────────────────────
async function loadChannels() {
  try {
    const acc = await loadAccount(true);
    const tg = (acc.channels || []).find((c) => c.type === "telegram");
    if (tg) {
      $("tg-badge").className = "badge " + (tg.is_active ? "green" : "red");
      $("tg-badge").textContent = tg.is_active ? "Active" : "Inactive";
      $("tg-info").innerHTML = "";
      const p = document.createElement("p");
      p.className = "channel-desc";
      if (tg.bot && tg.bot.username) {
        p.innerHTML = "";
        const b = document.createElement("b");
        b.textContent = (tg.bot.name || "Bot") + " (@" + tg.bot.username + ")";
        p.appendChild(b);
        p.appendChild(document.createTextNode(
          " · connected " +
          (tg.created_at ? new Date(tg.created_at).toLocaleDateString() : "")
        ));
        const link = document.createElement("a");
        link.href = "https://t.me/" + tg.bot.username;
        link.target = "_blank";
        link.textContent = "Open chat ↗";
        link.style.marginLeft = "10px";
        p.appendChild(link);
      } else {
        p.textContent = "Bot token " + tg.token_hint + " · connected " +
          (tg.created_at ? new Date(tg.created_at).toLocaleDateString() : "");
      }
      $("tg-info").appendChild(p);
    } else {
      $("tg-badge").className = "badge";
      $("tg-badge").textContent = "Not set up";
      $("tg-info").textContent = "No Telegram bot connected.";
    }
    waRefreshBadge();
  } catch (e) {
    $("tg-badge").className = "badge red";
    $("tg-badge").textContent = "Error";
    $("tg-info").textContent = "Could not load channel info (" + e.message + "). It will retry when you reopen this tab.";
  }
}

// ── WhatsApp (QR linking) ────────────────────────────────────────────────────
let _waPollTimer = null;
let _waQrUrl = null;

function waStopPolling() {
  if (_waPollTimer) { clearInterval(_waPollTimer); _waPollTimer = null; }
}

function waHideQr() {
  $("wa-qr-wrap").hidden = true;
  if (_waQrUrl) { URL.revokeObjectURL(_waQrUrl); _waQrUrl = null; }
}

function waSetBadge(kind, text) {
  $("wa-badge").className = "badge " + kind;
  $("wa-badge").textContent = text;
}

async function waRefreshBadge() {
  try {
    const auth = getAuth();
    const d = await api("/api/whatsapp/status?business_id=" + encodeURIComponent(auth.businessId));
    if (d.status === "WORKING") waSetBadge("green", "Connected" + (d.phone ? " · " + d.phone : ""));
    else if (d.status === "SCAN_QR_CODE") waSetBadge("amber", "Waiting for QR scan");
    else if (d.status === "NOT_CONNECTED") waSetBadge("", "Not connected");
    else waSetBadge("amber", d.status);
  } catch {
    waSetBadge("", "Unavailable");
  }
}

async function waShowQr() {
  const auth = getAuth();
  try {
    const r = await fetch("/api/whatsapp/qr?business_id=" + encodeURIComponent(auth.businessId), {
      headers: await authHeaders(),
    });
    if (r.status === 401 || r.status === 403) {
      // Auth problem is not transient — stop polling and tell the user
      waStopPolling(); waHideQr();
      msg("wa-status", "err", "Sign-in expired — refresh the page and click Connect again.");
      return;
    }
    if (!r.ok) return; // not ready yet — next poll retries
    const blob = await r.blob();
    if (_waQrUrl) URL.revokeObjectURL(_waQrUrl);
    _waQrUrl = URL.createObjectURL(blob);
    $("wa-qr").src = _waQrUrl;
    $("wa-qr-wrap").hidden = false;
  } catch { /* transient */ }
}

async function waPoll() {
  const auth = getAuth();
  try {
    const d = await api("/api/whatsapp/status?business_id=" + encodeURIComponent(auth.businessId));
    if (d.status === "WORKING") {
      waStopPolling(); waHideQr();
      waSetBadge("green", "Connected" + (d.phone ? " · " + d.phone : ""));
      msg("wa-status", "ok", "✓ WhatsApp linked" + (d.name ? " (" + d.name + ")" : "") + ". Your assistant now answers there too.");
    } else if (d.status === "SCAN_QR_CODE") {
      waSetBadge("amber", "Waiting for QR scan");
      msg("wa-status", "warn", "Scan the QR with WhatsApp on your phone — the code refreshes automatically.");
      waShowQr();
    } else if (d.status === "FAILED") {
      waStopPolling(); waHideQr();
      waSetBadge("red", "Failed");
      msg("wa-status", "err", "Session failed — click Connect to retry.");
    } else {
      msg("wa-status", "", "Session status: " + d.status + "…");
    }
  } catch (e) {
    waStopPolling(); waHideQr();
    msg("wa-status", "err", "Error: " + e.message);
  }
}

async function waConnect(attempt = 1) {
  const auth = getAuth();
  const btn = $("wa-connect-btn");
  btn.disabled = true;
  waStopPolling(); waHideQr();
  msg("wa-status", "warn", attempt === 1
    ? "Starting WhatsApp session…"
    : "Bridge is waking — retrying (attempt " + attempt + " of 6)…");
  try {
    await api("/api/whatsapp/connect", {
      method: "POST",
      body: JSON.stringify({ business_id: auth.businessId }),
    });
    waPoll();
    _waPollTimer = setInterval(waPoll, 3000);
    setTimeout(() => {
      if (_waPollTimer) {
        waStopPolling(); waHideQr();
        msg("wa-status", "warn", "QR expired / timed out — click Connect to try again.");
      }
    }, 180000);
    btn.disabled = false;
  } catch (e) {
    // The free-tier bridge takes ~30-60s to cold-start; keep retrying for the user
    if (/waking|waking up|unreachable|502|503|network/i.test(e.message) && attempt < 6) {
      let secs = 20;
      msg("wa-status", "warn", "WhatsApp bridge is waking up — retrying in " + secs + "s…");
      const tick = setInterval(() => {
        secs--;
        if (secs > 0) msg("wa-status", "warn", "WhatsApp bridge is waking up — retrying in " + secs + "s…");
      }, 1000);
      setTimeout(() => { clearInterval(tick); waConnect(attempt + 1); }, 20000);
    } else {
      msg("wa-status", "err", "Connect failed: " + e.message);
      btn.disabled = false;
    }
  }
}

async function waDisconnect() {
  const auth = getAuth();
  waStopPolling(); waHideQr();
  msg("wa-status", "", "Disconnecting…");
  try {
    await api("/api/whatsapp/disconnect", {
      method: "POST",
      body: JSON.stringify({ business_id: auth.businessId }),
    });
    waSetBadge("", "Not connected");
    msg("wa-status", "ok", "✓ WhatsApp unlinked.");
  } catch (e) {
    msg("wa-status", "err", "Disconnect failed: " + e.message);
  }
}

// ── API Keys tab ─────────────────────────────────────────────────────────────
async function renderKeys() {
  try {
    const acc = await loadAccount(true);
    $("key-provider").textContent = acc.api_key ? acc.api_key.provider : "none";
    $("key-date").textContent = acc.api_key && acc.api_key.created_at
      ? new Date(acc.api_key.created_at).toLocaleString() : "—";
  } catch (e) {
    msg("key-msg", "err", "Error: " + e.message);
  }
}

async function replaceKey() {
  const auth = getAuth();
  const key = $("key-new").value.trim();
  if (!key) return msg("key-msg", "err", "Enter the new API key.");
  msg("key-msg", "warn", "Saving…");
  try {
    const d = await api("/api/api-key", {
      method: "PUT",
      body: JSON.stringify({ business_id: auth.businessId, api_key: key }),
    });
    $("key-new").value = "";
    msg("key-msg", "ok", "✓ Key replaced (provider: " + d.provider + ").");
    renderKeys();
  } catch (e) {
    msg("key-msg", "err", "Error: " + e.message);
  }
}

// ── Personality tab ──────────────────────────────────────────────────────────
function fillTimezoneSelect(selectId, selected) {
  const sel = $(selectId);
  const browserTz = Intl.DateTimeFormat().resolvedOptions().timeZone;
  let zones = ["UTC"];
  try {
    zones = Intl.supportedValuesOf("timeZone");
  } catch (e) {
    if (browserTz) zones.push(browserTz);
  }
  sel.innerHTML = "";
  for (const z of zones) {
    const opt = document.createElement("option");
    opt.value = z;
    opt.textContent = z.replace(/_/g, " ");
    sel.appendChild(opt);
  }
  sel.value = selected || browserTz || "UTC";
  if (!sel.value) sel.value = "UTC";
}

async function renderPersonality() {
  try {
    const acc = await loadAccount(true);
    const cfg = acc.config || {};
    setModel("p-model", "p-model-custom", cfg.llm_model || "openai/gpt-4o-mini");
    const temp = cfg.temperature != null ? cfg.temperature : 0.7;
    $("p-temp").value = temp;
    $("p-temp-val").textContent = temp;
    $("p-prompt").value = cfg.system_prompt_override || "";
    fillTimezoneSelect("p-timezone", cfg.timezone);
  } catch (e) {
    msg("p-msg", "err", "Error: " + e.message);
  }
}

async function savePersonality() {
  const auth = getAuth();
  const model = readModel("p-model", "p-model-custom");
  if (!model) return msg("p-msg", "err", "Model is required.");
  msg("p-msg", "warn", "Saving…");
  try {
    await api("/api/config", {
      method: "PUT",
      body: JSON.stringify({
        business_id: auth.businessId,
        llm_model: model,
        temperature: parseFloat($("p-temp").value),
        system_prompt: $("p-prompt").value.trim() || null,
        timezone: $("p-timezone").value || null,
      }),
    });
    msg("p-msg", "ok", "✓ Personality saved — takes effect on the next customer message.");
  } catch (e) {
    msg("p-msg", "err", "Error: " + e.message);
  }
}

// ── Conversations (inbox) ────────────────────────────────────────────────────
const CH_ICON = { telegram: "✈️", whatsapp: "💬" };
const CH_LABEL = { telegram: "Telegram", whatsapp: "WhatsApp" };
let _activeConvId = null;
let _allConvos = [];

function convDisplayName(c) {
  if (c.customer_name) return c.customer_name;
  const id = c.customer_id || "";
  // WhatsApp ids are unreadable raw; show a human label until the contact's
  // display name arrives with their next message.
  if (id.endsWith("@newsletter")) return "Channel …" + id.slice(-15, -11);
  if (id.endsWith("@lid")) return "Customer …" + id.slice(-8, -4);
  if (id.endsWith("@c.us")) return "+" + id.slice(0, -5);
  return id || "Unknown";
}

function fmtTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  const today = new Date();
  const sameDay = d.toDateString() === today.toDateString();
  return sameDay
    ? d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    : d.toLocaleDateString([], { day: "numeric", month: "short" });
}

async function loadConversations() {
  const auth = getAuth();
  const list = $("conv-list");
  list.innerHTML = '<div class="empty-state">Loading…</div>';
  try {
    const d = await api(
      "/api/conversations?business_id=" + encodeURIComponent(auth.businessId) + "&limit=100"
    );
    _allConvos = d.conversations || [];
    renderConvList();
  } catch (e) {
    list.innerHTML = '<div class="empty-state">Error: ' + e.message + "</div>";
  }
}

function renderConvList() {
  const list = $("conv-list");
  const filter = $("conv-filter").value;
  const convos = filter ? _allConvos.filter((c) => c.channel === filter) : _allConvos;
  $("conv-count").textContent = convos.length + (convos.length === 1 ? " chat" : " chats");
  list.innerHTML = "";
  if (!convos.length) {
    list.innerHTML =
      '<div class="empty-state"><div class="empty-icon">📭</div>' +
      (filter && _allConvos.length
        ? "<p>No " + (CH_LABEL[filter] || filter) + " conversations yet.</p>"
        : "<p>No conversations yet.<br>They appear here as soon as a customer messages your assistant.</p>") +
      "</div>";
    return;
  }
  convos.forEach((c) => list.appendChild(renderConvItem(c)));
}

function renderConvItem(c) {
  const item = document.createElement("button");
  item.className = "conv-item" + (c.id === _activeConvId ? " active" : "");
  item.dataset.convId = c.id;

  const avatar = document.createElement("div");
  const isNews = (c.customer_id || "").endsWith("@newsletter");
  avatar.className = "conv-avatar " + (isNews ? "av-news" : "av-" + (c.channel || "x"));
  avatar.textContent = isNews ? "📰" : convDisplayName(c).charAt(0).toUpperCase();

  const meta = document.createElement("div");
  meta.className = "conv-meta";
  const name = document.createElement("div");
  name.className = "conv-name";
  const ch = document.createElement("span");
  ch.className = "ch";
  ch.textContent = CH_ICON[c.channel] || "❓";
  ch.title = c.channel;
  name.appendChild(ch);
  name.appendChild(document.createTextNode(convDisplayName(c)));
  const preview = document.createElement("div");
  preview.className = "conv-preview";
  preview.textContent = c.last_message_preview
    ? (c.last_message_role === "assistant" ? "You: " : "") + c.last_message_preview
    : "No messages yet";
  meta.appendChild(name);
  meta.appendChild(preview);

  const side = document.createElement("div");
  side.className = "conv-side";
  const time = document.createElement("div");
  time.className = "conv-time";
  time.textContent = fmtTime(c.last_message_at);
  const count = document.createElement("span");
  count.className = "conv-count";
  count.textContent = c.message_count;
  side.appendChild(time);
  side.appendChild(count);

  item.appendChild(avatar);
  item.appendChild(meta);
  item.appendChild(side);
  item.onclick = () => openConversation(c);
  return item;
}

async function openConversation(c) {
  const auth = getAuth();
  _activeConvId = c.id;
  document.querySelectorAll(".conv-item").forEach((el) =>
    el.classList.toggle("active", el.dataset.convId === c.id)
  );
  $("inbox").classList.add("chat-open"); // mobile: show the chat pane
  $("chat-head").hidden = false;
  $("chat-peer-name").textContent = convDisplayName(c);
  $("chat-peer-sub").textContent =
    (CH_ICON[c.channel] || "") + " " + c.channel + " · " + (c.customer_id || "");
  const body = $("chat-body");
  body.innerHTML = '<div class="empty-state">Loading…</div>';
  try {
    const d = await api(
      "/api/conversations/" + encodeURIComponent(c.id) +
      "/messages?business_id=" + encodeURIComponent(auth.businessId) + "&limit=500"
    );
    body.innerHTML = "";
    (d.messages || []).forEach((m) => {
      const row = document.createElement("div");
      row.className = "bubble-row " + (m.role === "assistant" ? "assistant" : "user");
      const bubble = document.createElement("div");
      bubble.className = "bubble";
      bubble.textContent = m.content;
      const time = document.createElement("span");
      time.className = "bubble-time";
      time.textContent = m.created_at
        ? new Date(m.created_at).toLocaleString([], {
            day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
          })
        : "";
      bubble.appendChild(time);
      row.appendChild(bubble);
      body.appendChild(row);
    });
    if (!d.messages || !d.messages.length) {
      body.innerHTML = '<div class="empty-state">No messages in this conversation.</div>';
    }
    body.scrollTop = body.scrollHeight; // jump to the newest message
  } catch (e) {
    body.innerHTML = '<div class="empty-state">Error: ' + e.message + "</div>";
  }
}

function closeChat() {
  $("inbox").classList.remove("chat-open");
}

// ── Logs (activity feed) ─────────────────────────────────────────────────────
async function loadLogs() {
  const auth = getAuth();
  const list = $("log-list");
  list.innerHTML = '<div class="empty-state">Loading…</div>';
  try {
    const d = await api(
      "/api/logs?business_id=" + encodeURIComponent(auth.businessId) + "&limit=200"
    );
    _allLogs = d.logs || [];
    renderLogList();
  } catch (e) {
    list.innerHTML = '<div class="empty-state">Error: ' + e.message + "</div>";
  }
}

let _allLogs = [];

function renderLogList() {
  const list = $("log-list");
  const filter = $("log-filter").value;
  const logs = filter ? _allLogs.filter((l) => l.channel === filter) : _allLogs;
  $("logs-count").textContent = logs.length + " events";
  list.innerHTML = "";
  if (!logs.length) {
    list.innerHTML =
      '<div class="empty-state"><div class="empty-icon">📜</div>' +
      (filter && _allLogs.length
        ? "<p>No " + (CH_LABEL[filter] || filter) + " activity yet.</p>"
        : "<p>No activity yet — messages appear here in real time.</p>") +
      "</div>";
    return;
  }
  logs.forEach((l) => {
      const row = document.createElement("div");
      row.className = "log-row";

      const time = document.createElement("span");
      time.className = "log-time";
      time.textContent = l.created_at
        ? new Date(l.created_at).toLocaleString([], {
            day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit",
          })
        : "";

      const dir = document.createElement("span");
      dir.className = "log-dir " + (l.role === "assistant" ? "out" : "in");
      dir.textContent = l.role === "assistant" ? "OUT" : "IN";
      dir.title = l.role === "assistant" ? "Assistant reply" : "Customer message";

      const who = document.createElement("span");
      who.className = "log-who";
      const ch = document.createElement("span");
      ch.className = "ch";
      ch.textContent = CH_ICON[l.channel] || "";
      who.appendChild(ch);
      who.appendChild(document.createTextNode(convDisplayName(l)));

      const preview = document.createElement("span");
      preview.className = "log-preview";
      preview.textContent = l.preview || "";

      row.appendChild(time);
      row.appendChild(dir);
      row.appendChild(who);
      row.appendChild(preview);
      list.appendChild(row);
  });
}

// ── Boot ─────────────────────────────────────────────────────────────────────
async function boot() {
  fillModelSelect("su-model", "su-model-custom");
  fillModelSelect("p-model", "p-model-custom");

  // An owner session (from sign-in, setup, or token login) boots straight
  // into the app — no network round-trip needed.
  const auth = getAuth();
  if (auth && auth.ownerToken) return showAppView();

  let clientId = "";
  try {
    const cfg = await api("/api/public-config");
    clientId = (cfg && cfg.google_client_id) || "";
  } catch { /* backend without Google support */ }

  if (clientId) {
    try {
      await loadGoogleSignIn(clientId);
      _googleOn = true;
    } catch (e) { /* GIS unreachable — email/password still works */ }
  }

  // Restore an email/password session: account exists but which business?
  const acct = getAcct();
  if (acct && acct.token) {
    try {
      const d = await api("/api/auth/me");
      if (d.business) {
        setAuth({
          businessId: d.business.id,
          ownerToken: d.business.owner_token,
          businessName: d.business.name,
        });
        return showAppView();
      }
      return showOnboarding(d.account.email);
    } catch { clearAcct(); /* stale token — fall through to sign-up */ }
  }

  showSignUp();
}

boot();
