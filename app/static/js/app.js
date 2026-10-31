// CARE-MM SPA controller: auth, patients, on-device monitoring, alerts, history.
import { api, ApiError, login, logout, refresh, register, wsUrl } from "./api.js";
import { VoiceTap } from "./audio.js";

const $ = (id) => document.getElementById(id);
const el = (tag, props = {}, text) => {
  const n = Object.assign(document.createElement(tag), props);
  if (text !== undefined) n.textContent = text;
  return n;
};
const fmtTime = (iso) => new Date(iso).toLocaleString();

const state = {
  user: null, patients: [], patient: null,
  authMode: "login",
  mon: null,          // active Monitor instance
  watch: null,        // /ws/watch socket
  unack: 0,
  alertCursor: null,
  landmarkerPromise: null,
};

function toast(msg, ms = 3500) {
  const t = $("toast");
  t.textContent = msg; t.classList.remove("hidden");
  clearTimeout(toast._t); toast._t = setTimeout(() => t.classList.add("hidden"), ms);
}

function show(view) {
  for (const v of ["view-auth", "view-app"]) $(v).classList.toggle("hidden", v !== view);
}

// ============================ AUTH ============================
function setAuthMode(mode) {
  state.authMode = mode;
  document.querySelectorAll("[data-auth-tab]").forEach((b) => {
    const on = b.dataset.authTab === mode;
    b.classList.toggle("active", on); b.setAttribute("aria-selected", String(on));
  });
  document.querySelectorAll(".reg-only").forEach((n) => n.classList.toggle("hidden", mode !== "register"));
  $("auth-submit").textContent = mode === "login" ? "Sign in" : "Create account";
  $("form-auth").password.autocomplete = mode === "login" ? "current-password" : "new-password";
  $("auth-error").textContent = "";
}

async function onAuthSubmit(ev) {
  ev.preventDefault();
  const f = ev.target;
  $("auth-error").textContent = "";
  $("auth-submit").disabled = true;
  try {
    if (state.authMode === "login") await login(f.email.value.trim(), f.password.value);
    else await register(f.email.value.trim(), f.password.value, f.full_name.value.trim());
    f.password.value = "";
    await enterApp();
  } catch (e) {
    $("auth-error").textContent = e instanceof ApiError ? e.message : "Network error";
  } finally { $("auth-submit").disabled = false; }
}

async function enterApp() {
  state.user = await api("/api/auth/me");
  $("user-email").textContent = state.user.email;
  show("view-app");
  await loadPatients();
}

async function doLogout() {
  await stopMonitoring();
  closeWatch();
  await logout().catch(() => {});
  state.user = null; state.patient = null;
  show("view-auth");
}

// ============================ PATIENTS ============================
async function loadPatients() {
  state.patients = await api("/api/patients?limit=200");
  renderPatients();
}

function renderPatients() {
  const ul = $("patient-list");
  ul.replaceChildren();
  if (!state.patients.length) ul.append(el("li", { className: "muted" }, "No patients yet."));
  for (const p of state.patients) {
    const li = el("li", { tabIndex: 0 }, p.display_name);
    if (state.patient && state.patient.id === p.id) li.classList.add("active");
    li.addEventListener("click", () => selectPatient(p));
    li.addEventListener("keydown", (e) => { if (e.key === "Enter") selectPatient(p); });
    ul.append(li);
  }
}

async function selectPatient(p) {
  if (state.mon && state.patient && state.patient.id !== p.id) {
    if (!confirm("Stop the current monitoring session and switch patient?")) return;
    await stopMonitoring();
  }
  state.patient = p;
  renderPatients();
  $("empty-state").classList.add("hidden");
  $("patient-panel").classList.remove("hidden");
  $("patient-name").textContent = p.display_name;
  resetMonitorUI();
  setTab("monitor");
  state.unack = 0; updateUnack();
  openWatch();
  api(`/api/patients/${p.id}/alerts?unacknowledged=true&limit=200`)
    .then((a) => { state.unack = a.length; updateUnack(); }).catch(() => {});
}

async function onAddPatient(ev) {
  ev.preventDefault();
  const name = ev.target.display_name.value.trim();
  if (!name) return;
  try {
    const p = await api("/api/patients", { method: "POST", body: { display_name: name } });
    ev.target.reset();
    state.patients.unshift(p);
    selectPatient(p);
  } catch (e) { toast(e.message); }
}

function setTab(tab) {
  document.querySelectorAll("[data-tab]").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  document.querySelectorAll("[data-pane]").forEach((p) => p.classList.toggle("hidden", p.dataset.pane !== tab));
  if (tab === "alerts") loadAlerts(true);
  if (tab === "history") loadHistory();
}

// ============================ LIVE ALERT WATCH ============================
function closeWatch() {
  if (state.watch) { state.watch.onclose = null; state.watch.close(); state.watch = null; }
}

async function openWatch(attempt = 0) {
  closeWatch();
  const p = state.patient;
  if (!p) return;
  try {
    const t = await api(`/api/patients/${p.id}/watch-ticket`, { method: "POST" });
    if (state.patient !== p) return;
    const ws = new WebSocket(wsUrl(t.ws_path, t.ws_ticket));
    state.watch = ws;
    ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.type !== "alert") return;
      state.unack += 1; updateUnack();
      if (!state.mon) pushLiveAlert(msg);  // monitor view shows its own stream
      if (msg.level === "urgent") toast(`URGENT: ${msg.reason}`, 8000);
    };
    ws.onclose = () => {
      if (state.watch === ws && state.patient === p) setTimeout(() => openWatch(attempt + 1), Math.min(30000, 1000 * 2 ** attempt));
    };
  } catch (_) {
    setTimeout(() => state.patient === p && openWatch(attempt + 1), Math.min(30000, 1000 * 2 ** attempt));
  }
}

function updateUnack() {
  const c = $("alert-count");
  c.textContent = String(state.unack);
  c.classList.toggle("hidden", state.unack <= 0);
}

// ============================ MONITOR ============================
let trendChart = null;
function ensureTrendChart() {
  if (trendChart || !window.Chart) return;
  trendChart = new Chart($("trend-chart"), {
    type: "line",
    data: { labels: [], datasets: [
      { label: "Pain (PSPI/16)", data: [], borderColor: "#ef4444", borderWidth: 2, pointRadius: 0, tension: .3 },
      { label: "Comfort", data: [], borderColor: "#10b981", borderWidth: 2, pointRadius: 0, tension: .3 },
      { label: "Arousal", data: [], borderColor: "#6366f1", borderWidth: 2, pointRadius: 0, tension: .3 },
    ] },
    options: { animation: false, responsive: true, maintainAspectRatio: false,
      scales: { x: { ticks: { color: "#8a96bd", maxTicksLimit: 6 }, grid: { color: "rgba(255,255,255,.05)" } },
                y: { min: 0, max: 1, ticks: { color: "#8a96bd" }, grid: { color: "rgba(255,255,255,.05)" } } },
      plugins: { legend: { labels: { color: "#e6ecff" } } } },
  });
}

function getLandmarker() {
  if (!state.landmarkerPromise) {
    state.landmarkerPromise = import("./vision.js").then(async (v) => ({ v, ...(await v.createLandmarker()) }));
    state.landmarkerPromise.catch(() => { state.landmarkerPromise = null; });
  }
  return state.landmarkerPromise;
}

class Monitor {
  constructor(patient) {
    this.patient = patient;
    this.session = null; this.ws = null; this.stream = null; this.voice = null;
    this.extractor = null; this.contract = null;
    this.samples = []; this.pendingAudio = null; this.pendingText = null;
    this.timer = null; this.flushTimer = null; this.pingTimer = null;
    this.stopped = false; this.reconnects = 0;
    this.fpsWin = [];
  }

  async start(withMic) {
    setMsg("Loading on-device face model…");
    const [{ v, landmarker, delegate }, media] = await Promise.all([
      getLandmarker(),
      navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 640 }, height: { ideal: 480 }, frameRate: { ideal: 30 } },
        audio: withMic ? { channelCount: 1, echoCancellation: true, noiseSuppression: true } : false,
      }),
    ]);
    this.stream = media;
    $("m-engine").textContent = `WASM/${delegate}`;
    const video = $("video");
    video.srcObject = media;
    await video.play();
    $("video-overlay").classList.add("hidden");

    const r = await api("/api/sessions", { method: "POST",
      body: { patient_id: this.patient.id, consent_confirmed: true } });
    this.session = r.session;
    await this.connect(r.ws_path, r.ws_ticket);

    this.extractor = new v.FeatureExtractor(landmarker, this.contract, $("sample-canvas"));
    if (media.getAudioTracks().length) {
      this.voice = new VoiceTap(media, (f) => { this.pendingAudio = f; });
      await this.voice.start().catch((e) => { console.warn("voice disabled:", e); this.voice = null; });
    }
    const interval = 1000 / (this.contract.target_fps || 10);
    this.timer = setInterval(() => this.tick(), interval);
    this.flushTimer = setInterval(() => this.flush(), this.contract.batch_interval_ms || 500);
    this.pingTimer = setInterval(() => this.send({ type: "ping" }), 20000);
    setMsg("Monitoring. Video and audio stay on this device.");
  }

  connect(path, ticket) {
    return new Promise((resolve, reject) => {
      const ws = new WebSocket(wsUrl(path, ticket));
      this.ws = ws;
      let opened = false;
      ws.onmessage = (ev) => {
        const msg = JSON.parse(ev.data);
        if (msg.type === "hello") {
          this.contract = msg; opened = true; this.reconnects = 0;
          setConn("streaming", true); resolve();
        } else if (msg.type === "result") renderResult(msg.data);
        else if (msg.type === "summary") renderSummary(msg.text);
        else if (msg.type === "throttled") { /* server back-pressure: next flush carries more */ }
        else if (msg.type === "error") {
          console.warn("server:", msg);
          if (msg.code === "consent_revoked" || msg.code === "consent_required") setMsg("Consent no longer valid — monitoring stopped.");
          if (!opened) reject(new Error(msg.code));
        }
      };
      ws.onclose = (ev) => {
        setConn("disconnected", false);
        if (!opened) { reject(new Error(`connect failed (${ev.code})`)); return; }
        if (!this.stopped && ![4401, 4403, 4404, 4429].includes(ev.code)) this.reconnect();
        else if (!this.stopped) stopMonitoring();
      };
    });
  }

  async reconnect() {
    if (this.stopped) return;
    const delay = Math.min(15000, 500 * 2 ** this.reconnects++);
    setConn(`reconnecting in ${Math.round(delay / 1000)}s`, false);
    await new Promise((r) => setTimeout(r, delay));
    if (this.stopped) return;
    try {
      const t = await api(`/api/sessions/${this.session.id}/ticket`, { method: "POST" });
      await this.connect(t.ws_path, t.ws_ticket);
    } catch (e) {
      if (e instanceof ApiError && (e.status === 403 || e.status === 404)) { stopMonitoring(); return; }
      this.reconnect();
    }
  }

  tick() {
    const video = $("video");
    if (!this.extractor || video.readyState < 2) return;
    try {
      const s = this.extractor.extract(video);
      this.samples.push(s);
      const max = this.contract.max_samples_per_batch || 40;
      if (this.samples.length > max) this.samples.splice(0, this.samples.length - max);
      const now = performance.now();
      this.fpsWin.push(now);
      while (this.fpsWin.length && now - this.fpsWin[0] > 2000) this.fpsWin.shift();
      $("m-fps").textContent = (this.fpsWin.length / 2).toFixed(1);
      $("m-face").textContent = s.bs ? "yes" : "no";
    } catch (e) { console.warn("extract error", e); }
  }

  flush() {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
    if (!this.samples.length && !this.pendingAudio && !this.pendingText) return;
    const msg = { type: "batch", samples: this.samples.splice(0) };
    if (this.pendingAudio) { msg.audio = this.pendingAudio; this.pendingAudio = null; }
    if (this.pendingText) { msg.text = this.pendingText; this.pendingText = null; }
    this.send(msg);
  }

  send(obj) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN && this.ws.bufferedAmount < 256 * 1024) {
      this.ws.send(JSON.stringify(obj));
    }
  }

  async stop({ revoke = false } = {}) {
    this.stopped = true;
    clearInterval(this.timer); clearInterval(this.flushTimer); clearInterval(this.pingTimer);
    this.flush();
    if (this.voice) await this.voice.stop();
    if (this.stream) this.stream.getTracks().forEach((t) => t.stop());
    if (this.ws) { this.ws.onclose = null; this.ws.close(1000); }
    if (this.session) {
      const path = revoke ? "revoke" : "end";
      await api(`/api/sessions/${this.session.id}/${path}`, { method: "POST" }).catch(() => {});
    }
    $("video").srcObject = null;
    $("video-overlay").classList.remove("hidden");
    setConn("idle", null);
  }
}

function setMsg(t) { $("monitor-msg").textContent = t; }
function setConn(text, ok) {
  const c = $("conn-status");
  c.textContent = text;
  c.classList.toggle("ok", ok === true); c.classList.toggle("bad", ok === false);
}

function updateMonitorButtons() {
  const running = !!state.mon;
  $("btn-start").disabled = running || !$("consent-check").checked;
  $("btn-stop").disabled = !running;
  $("btn-revoke").disabled = !running;
  $("consent-check").disabled = running;
  $("mic-check").disabled = running;
}

async function startMonitoring() {
  if (state.mon || !state.patient) return;
  if (!window.isSecureContext) { toast("Camera access requires HTTPS."); return; }
  state.mon = new Monitor(state.patient);
  updateMonitorButtons();
  ensureTrendChart();
  try {
    await state.mon.start($("mic-check").checked);
  } catch (e) {
    console.error(e);
    const m = e && e.name === "NotAllowedError" ? "Camera/microphone permission denied." : `Could not start: ${e.message || e}`;
    setMsg(m); toast(m);
    await stopMonitoring();
  }
}

async function stopMonitoring(opts) {
  const m = state.mon;
  state.mon = null;
  if (m) await m.stop(opts);
  updateMonitorButtons();
}

function resetMonitorUI() {
  for (const id of ["k-pspi", "k-hr", "k-blink", "k-tag", "v-comfort", "v-arousal", "v-pain", "v-engagement",
    "voice-state", "note-state", "head-pose", "gaze"]) $(id).textContent = "–";
  for (const id of ["k-pain-level", "k-hr-q", "k-tag-conf", "voice-detail"]) $(id).textContent = "";
  for (const id of ["b-comfort", "b-arousal", "b-pain", "b-engagement"]) $(id).style.width = "0";
  $("summary").textContent = "Awaiting signals…"; $("summary").classList.remove("live");
  $("observations").replaceChildren(); $("active-aus").replaceChildren();
  $("live-alerts").replaceChildren(el("li", { className: "muted" }, "No alerts."));
  setMsg("");
  if (trendChart) { trendChart.data.labels = []; trendChart.data.datasets.forEach((d) => { d.data = []; }); trendChart.update(); }
  updateMonitorButtons();
}

function chips(ul, items) {
  ul.replaceChildren(...items.slice(0, 24).map((t) => el("li", {}, t)));
}

function setBar(name, v) {
  $(`b-${name}`).style.width = `${Math.round((v || 0) * 100)}%`;
  $(`v-${name}`).textContent = v == null ? "–" : v.toFixed(2);
}

function renderResult(d) {
  if (d.face_detected && d.pain && d.distress) {
    $("k-pspi").textContent = d.pain.pspi.toFixed(1);
    $("k-pain-level").textContent = `${d.pain.level} · ${d.pain.trend}`;
    $("k-blink").textContent = d.blink_rpm.toFixed(0);
    $("k-tag").textContent = d.distress.tag.replaceAll("_", " ");
    $("k-tag-conf").textContent = `confidence ${(d.distress.confidence * 100).toFixed(0)}%`;
    setBar("comfort", d.distress.comfort); setBar("arousal", d.distress.arousal);
    setBar("pain", d.distress.pain); setBar("engagement", d.distress.engagement);
    chips($("observations"), d.distress.observations);
    chips($("active-aus"), d.active_aus.map((a) => `${a} ${(d.action_units[a] || 0).toFixed(2)}`));
    if (d.head_pose && d.head_pose.yaw !== undefined) {
      $("head-pose").textContent = `yaw ${d.head_pose.yaw.toFixed(0)}°, pitch ${d.head_pose.pitch.toFixed(0)}°, roll ${d.head_pose.roll.toFixed(0)}°`;
    }
    if (d.gaze && d.gaze.averted !== undefined) $("gaze").textContent = d.gaze.averted ? "yes" : "no";
    if (trendChart) {
      const ds = trendChart.data;
      ds.labels.push(new Date(d.ts * 1000).toLocaleTimeString());
      ds.datasets[0].data.push(d.distress.pain); ds.datasets[1].data.push(d.distress.comfort);
      ds.datasets[2].data.push(d.distress.arousal);
      if (ds.labels.length > 240) { ds.labels.shift(); ds.datasets.forEach((x) => x.data.shift()); }
      trendChart.update("none");
    }
  }
  if (d.heart_rate && d.heart_rate.quality) {
    const ok = d.heart_rate.quality !== "poor";
    $("k-hr").textContent = ok ? d.heart_rate.bpm.toFixed(0) : "–";
    $("k-hr-q").textContent = `signal ${d.heart_rate.quality}${d.heart_rate.is_abnormal ? " · " + d.heart_rate.abnormality : ""}`;
  }
  if (d.voice && d.voice.vocal_state) {
    $("voice-state").textContent = d.voice.vocal_state;
    $("voice-detail").textContent = `(arousal ${d.voice.arousal.toFixed(2)}, valence ${d.voice.valence.toFixed(2)})`;
  }
  if (d.text && d.text.valence !== undefined) {
    const parts = [`valence ${d.text.valence.toFixed(2)}`];
    if (d.text.pain_mentioned) parts.push("pain mentioned");
    if (d.text.distress_mentioned) parts.push("distress mentioned");
    $("note-state").textContent = parts.join(" · ");
  }
  for (const a of d.alerts || []) pushLiveAlert({ ...a, created_at: new Date(a.ts * 1000).toISOString() });
}

function renderSummary(text) {
  $("summary").textContent = text;
  $("summary").classList.add("live");
}

function alertItem(a, withAck) {
  const li = el("li", { className: a.level });
  const meta = el("div", { className: "meta" });
  meta.append(el("span", {}, `${a.level.toUpperCase()} · ${a.key.replaceAll("_", " ")}`),
    el("span", {}, fmtTime(a.created_at)));
  li.append(meta, el("div", {}, a.reason));
  if (withAck && a.id) {
    if (a.acknowledged_at) li.append(el("div", { className: "meta" }, `acknowledged ${fmtTime(a.acknowledged_at)}`));
    else {
      const b = el("button", { className: "btn ghost ack" }, "Acknowledge");
      b.addEventListener("click", async () => {
        try {
          const r = await api(`/api/alerts/${a.id}/ack`, { method: "POST" });
          b.replaceWith(el("div", { className: "meta" }, `acknowledged ${fmtTime(r.acknowledged_at)}`));
          state.unack = Math.max(0, state.unack - 1); updateUnack();
        } catch (e) { toast(e.message); }
      });
      li.append(b);
    }
  }
  return li;
}

function pushLiveAlert(a) {
  const ul = $("live-alerts");
  if (ul.firstChild && ul.firstChild.classList.contains("muted")) ul.replaceChildren();
  ul.prepend(alertItem(a, true));
  while (ul.children.length > 50) ul.lastChild.remove();
}

// ============================ ALERT HISTORY ============================
async function loadAlerts(reset) {
  const p = state.patient;
  if (!p) return;
  if (reset) { state.alertCursor = null; $("alert-history").replaceChildren(); }
  const q = new URLSearchParams({ limit: "50" });
  if ($("only-unack").checked) q.set("unacknowledged", "true");
  if (state.alertCursor) q.set("before", state.alertCursor);
  try {
    const rows = await api(`/api/patients/${p.id}/alerts?${q}`);
    const ul = $("alert-history");
    if (reset && !rows.length) ul.append(el("li", { className: "muted" }, "No alerts recorded."));
    rows.forEach((a) => ul.append(alertItem(a, true)));
    state.alertCursor = rows.length ? rows[rows.length - 1].created_at : state.alertCursor;
    $("btn-more-alerts").classList.toggle("hidden", rows.length < 50);
  } catch (e) { toast(e.message); }
}

// ============================ HISTORY ============================
let historyChart = null;
async function loadHistory() {
  const p = state.patient;
  if (!p || !window.Chart) return;
  const hours = $("history-hours").value;
  const rows = await api(`/api/patients/${p.id}/metrics?hours=${hours}`).catch((e) => { toast(e.message); return []; });
  const labels = rows.map((r) => new Date(r.bucket_start).toLocaleString());
  const data = {
    labels,
    datasets: [
      { label: "Avg PSPI", data: rows.map((r) => r.avg_pspi), borderColor: "#ef4444", yAxisID: "y", pointRadius: 0 },
      { label: "Max PSPI", data: rows.map((r) => r.max_pspi), borderColor: "#f59e0b", yAxisID: "y", pointRadius: 0, borderDash: [4, 4] },
      { label: "Comfort", data: rows.map((r) => r.avg_comfort), borderColor: "#10b981", yAxisID: "y1", pointRadius: 0 },
      { label: "Heart rate", data: rows.map((r) => r.avg_hr), borderColor: "#38bdf8", yAxisID: "y2", pointRadius: 0, hidden: true },
    ],
  };
  if (historyChart) { historyChart.data = data; historyChart.update(); return; }
  historyChart = new Chart($("history-chart"), {
    type: "line", data,
    options: { animation: false, responsive: true, maintainAspectRatio: false, spanGaps: false,
      scales: {
        x: { ticks: { color: "#8a96bd", maxTicksLimit: 8 }, grid: { color: "rgba(255,255,255,.05)" } },
        y: { min: 0, max: 16, position: "left", title: { display: true, text: "PSPI", color: "#8a96bd" }, ticks: { color: "#8a96bd" } },
        y1: { min: 0, max: 1, position: "right", grid: { drawOnChartArea: false }, ticks: { color: "#8a96bd" } },
        y2: { display: false, min: 40, max: 160 },
      },
      plugins: { legend: { labels: { color: "#e6ecff" } } } },
  });
}

async function exportData() {
  const p = state.patient;
  try {
    const data = await api(`/api/patients/${p.id}/export`);
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const a = el("a", { href: URL.createObjectURL(blob), download: `care-mm-${p.display_name}-${Date.now()}.json` });
    document.body.append(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  } catch (e) { toast(e.message); }
}

async function deletePatient() {
  const p = state.patient;
  if (!confirm(`Permanently delete "${p.display_name}" and ALL associated sessions, alerts and metrics?`)) return;
  try {
    await stopMonitoring();
    closeWatch();
    await api(`/api/patients/${p.id}`, { method: "DELETE" });
    state.patients = state.patients.filter((x) => x.id !== p.id);
    state.patient = null;
    renderPatients();
    $("patient-panel").classList.add("hidden");
    $("empty-state").classList.remove("hidden");
    toast("Patient data deleted.");
  } catch (e) { toast(e.message); }
}

// ============================ WIRING ============================
function wire() {
  document.querySelectorAll("[data-auth-tab]").forEach((b) => b.addEventListener("click", () => setAuthMode(b.dataset.authTab)));
  $("form-auth").addEventListener("submit", onAuthSubmit);
  $("btn-logout").addEventListener("click", doLogout);
  $("form-patient").addEventListener("submit", onAddPatient);
  document.querySelectorAll("[data-tab]").forEach((b) => b.addEventListener("click", () => setTab(b.dataset.tab)));
  $("consent-check").addEventListener("change", updateMonitorButtons);
  $("btn-start").addEventListener("click", startMonitoring);
  $("btn-stop").addEventListener("click", () => stopMonitoring());
  $("btn-revoke").addEventListener("click", async () => {
    if (!confirm("Withdraw consent? Monitoring stops immediately and this session cannot be resumed.")) return;
    await stopMonitoring({ revoke: true });
    $("consent-check").checked = false; updateMonitorButtons();
    toast("Consent withdrawn.");
  });
  $("form-note").addEventListener("submit", (ev) => {
    ev.preventDefault();
    const t = ev.target.note.value.trim();
    if (!t) return;
    if (!state.mon) { toast("Start monitoring to include notes in the analysis."); return; }
    state.mon.pendingText = t; ev.target.reset(); toast("Note queued for analysis.");
  });
  $("only-unack").addEventListener("change", () => loadAlerts(true));
  $("btn-more-alerts").addEventListener("click", () => loadAlerts(false));
  $("history-hours").addEventListener("change", loadHistory);
  $("btn-export").addEventListener("click", exportData);
  $("btn-delete-patient").addEventListener("click", deletePatient);
  window.addEventListener("auth:expired", () => { toast("Session expired — please sign in again."); doLogout(); });
  window.addEventListener("beforeunload", () => { if (state.mon) state.mon.flush(); });
  document.addEventListener("visibilitychange", () => {
    if (document.hidden && state.mon) setMsg("Tab hidden — browsers may throttle analysis. Keep this tab visible.");
  });
}

async function boot() {
  wire();
  setAuthMode("login");
  if (await refresh()) {
    try { await enterApp(); return; } catch (_) { /* fall through */ }
  }
  show("view-auth");
}

boot();
