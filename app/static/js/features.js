// v3.1 feature views: PAINAD, care events + impact, care team, alarm settings,
// calibration, account security (2FA, password, audit log), notifications.
import { api, clearToken } from "./api.js";

let C = null;  // context injected by app.js: { state, toast, el, $, fmtTime, canDo, ... }

const PAINAD = {
  breathing: ["Normal", "Occasional laboured / short hyperventilation", "Noisy laboured / long hyperventilation / Cheyne-Stokes"],
  negative_vocalization: ["None", "Occasional moan/groan, negative speech", "Repeated calling out, loud moaning, crying"],
  facial_expression: ["Smiling or inexpressive", "Sad, frightened, frown", "Facial grimacing"],
  body_language: ["Relaxed", "Tense, distressed pacing, fidgeting", "Rigid, fists clenched, knees up, pulling away, striking out"],
  consolability: ["No need to console", "Distracted or reassured by voice/touch", "Unable to console, distract or reassure"],
};
const INTERP = (t) => (t <= 0 ? "no pain behaviours" : t <= 3 ? "mild" : t <= 6 ? "moderate" : "severe");
const EVENT_KINDS = { medication: "Medication", repositioning: "Repositioned", comfort_measure: "Comfort measure",
  meal: "Meal / fluids", toileting: "Toileting", visit: "Visit", sleep: "Sleep", other: "Other" };
const ALERT_KEYS = ["severe_pain", "moderate_pain", "tachycardia", "bradycardia", "tachypnea", "bradypnea",
  "vocal_distress", "low_comfort"];
const touched = new Set();
let lastAuto = {};

export function init(ctx) {
  C = ctx;
  const { $, el } = C;

  // PAINAD selects
  const f = $("form-painad");
  for (const [name, opts] of Object.entries(PAINAD)) {
    const sel = f.elements[name];
    opts.forEach((label, i) => sel.append(el("option", { value: String(i) }, `${i} — ${label}`)));
    sel.addEventListener("change", () => { touched.add(name); sel.classList.remove("suggested"); updatePainadTotal(); });
  }
  f.addEventListener("submit", submitPainad);

  // Care event quick buttons
  const box = $("event-buttons");
  for (const [kind, label] of Object.entries(EVENT_KINDS)) {
    const b = el("button", { type: "button" }, label);
    b.addEventListener("click", () => logEvent(kind));
    box.append(b);
  }

  // Notifications
  if ("Notification" in window && Notification.permission !== "granted") {
    $("btn-notify").classList.remove("hidden");
    $("btn-notify").addEventListener("click", async () => {
      const p = await Notification.requestPermission();
      if (p === "granted") { $("btn-notify").classList.add("hidden"); C.toast("Desktop notifications enabled."); }
    });
  }

  // Team / settings / baseline
  $("form-member").addEventListener("submit", addMember);
  $("form-settings").addEventListener("submit", saveSettings);
  const mb = $("muted-boxes");
  for (const k of ALERT_KEYS) {
    const lab = el("label");
    lab.append(el("input", { type: "checkbox", value: k, name: "muted" }), document.createTextNode(k.replaceAll("_", " ")));
    mb.append(lab);
  }
  $("btn-reset-baseline").addEventListener("click", resetBaseline);

  // Account
  $("btn-mfa-setup").addEventListener("click", mfaSetup);
  $("form-mfa-enable").addEventListener("submit", mfaEnable);
  $("form-mfa-disable").addEventListener("submit", mfaDisable);
  $("form-password").addEventListener("submit", changePassword);
}

// ---------------------------------------------------------------- PAINAD
export function resetPainad() {
  touched.clear(); lastAuto = {};
  const f = C.$("form-painad");
  for (const name of Object.keys(PAINAD)) { f.elements[name].value = "0"; f.elements[name].classList.remove("suggested"); }
  f.elements.note.value = "";
  updatePainadTotal();
}

/** Pre-fill sensed items as suggestions unless the caregiver already chose a value. */
export function suggestPainad(items) {
  const f = C.$("form-painad");
  lastAuto = items;
  for (const [name, v] of Object.entries(items)) {
    if (v === null || v === undefined || touched.has(name)) continue;
    f.elements[name].value = String(v);
    f.elements[name].classList.add("suggested");
  }
  updatePainadTotal();
}

function updatePainadTotal() {
  const f = C.$("form-painad");
  const t = Object.keys(PAINAD).reduce((s, n) => s + Number(f.elements[n].value || 0), 0);
  C.$("painad-total").textContent = String(t);
  C.$("painad-interp").textContent = `(${INTERP(t)})`;
}

async function submitPainad(ev) {
  ev.preventDefault();
  const p = C.state.patient;
  const f = ev.target;
  if (!touched.has("body_language") || !touched.has("consolability")) {
    if (!confirm("Body language and consolability have not been explicitly rated. Record the assessment anyway?")) return;
  }
  const body = Object.fromEntries(Object.keys(PAINAD).map((n) => [n, Number(f.elements[n].value)]));
  body.auto_items = lastAuto;
  body.note = f.elements.note.value.trim() || null;
  const sid = C.currentSessionId();
  if (sid) body.session_id = sid;
  try {
    const r = await api(`/api/patients/${p.id}/assessments`, { method: "POST", body });
    C.toast(`PAINAD recorded: ${r.total}/10 (${r.interpretation.replaceAll("_", " ")})`);
    resetPainad();
  } catch (e) { C.toast(e.message); }
}

// ---------------------------------------------------------------- care events
async function logEvent(kind) {
  const p = C.state.patient;
  const note = C.$("event-note").value.trim() || null;
  try {
    await api(`/api/patients/${p.id}/events`, { method: "POST", body: { kind, note } });
    C.$("event-note").value = "";
    C.toast(`${EVENT_KINDS[kind]} logged.`);
  } catch (e) { C.toast(e.message); }
}

function fmt(v, d = 2) { return v === null || v === undefined ? "–" : Number(v).toFixed(d); }

async function showImpact(p, ev) {
  const box = C.$("impact-box");
  try {
    const r = await api(`/api/patients/${p.id}/events/${ev.id}/impact`);
    const row = (label, a, b, d) => {
      const tr = C.el("tr");
      [label, fmt(a, d), fmt(b, d)].forEach((t, i) => tr.append(C.el(i ? "td" : "td", {}, t)));
      return tr;
    };
    const table = C.el("table");
    const head = C.el("tr");
    ["", `${r.before.minutes} min before`, `${r.after.minutes} min after`].forEach((t) => head.append(C.el("th", {}, t)));
    table.append(head,
      row("Avg PSPI", r.before.avg_pspi, r.after.avg_pspi),
      row("Max PSPI", r.before.max_pspi, r.after.max_pspi),
      row("Comfort", r.before.avg_comfort, r.after.avg_comfort),
      row("Heart rate", r.before.avg_hr, r.after.avg_hr, 0),
      row("Respiration", r.before.avg_rr, r.after.avg_rr, 0),
      row("Alerts", r.before.alerts, r.after.alerts, 0));
    box.replaceChildren(C.el("b", {}, `${EVENT_KINDS[ev.kind] || ev.kind} — ${C.fmtTime(ev.occurred_at)}`), table,
      C.el("p", { className: "small muted" }, r.note));
    box.classList.remove("hidden");
  } catch (e) { C.toast(e.message); }
}

export async function loadHistoryExtras(p, isOwner) {
  if (!p) return;
  const { $, el } = C;
  const [events, painad] = await Promise.all([
    api(`/api/patients/${p.id}/events?hours=168`).catch(() => []),
    api(`/api/patients/${p.id}/assessments?limit=50`).catch(() => []),
  ]);
  $("impact-box").classList.add("hidden");
  const ul = $("event-list");
  ul.replaceChildren(...(events.length ? events.map((ev) => {
    const li = el("li", { className: "attention" });
    const meta = el("div", { className: "meta" });
    meta.append(el("span", {}, EVENT_KINDS[ev.kind] || ev.kind), el("span", {}, C.fmtTime(ev.occurred_at)));
    const b = el("button", { className: "btn ghost ack" }, "Before / after");
    b.addEventListener("click", () => showImpact(p, ev));
    li.append(meta, el("div", {}, ev.note || ""), b);
    return li;
  }) : [el("li", { className: "muted" }, "No care events in the last 7 days.")]));
  const pl = $("painad-list");
  pl.replaceChildren(...(painad.length ? painad.map((a) => {
    const lvl = a.total >= 7 ? "urgent" : a.total >= 4 ? "concern" : "attention";
    const li = el("li", { className: lvl });
    const meta = el("div", { className: "meta" });
    meta.append(el("span", {}, `PAINAD ${a.total}/10 · ${a.interpretation.replaceAll("_", " ")}`),
      el("span", {}, C.fmtTime(a.created_at)));
    li.append(meta, el("div", { className: "small" },
      `B${a.breathing} V${a.negative_vocalization} F${a.facial_expression} BL${a.body_language} C${a.consolability}`
      + (a.note ? ` — ${a.note}` : "")));
    return li;
  }) : [el("li", { className: "muted" }, "No assessments recorded.")]));
  if (isOwner) renderAudit($("patient-audit"), await api(`/api/patients/${p.id}/audit?limit=200`).catch(() => []), true);
}

function renderAudit(ul, rows, showUser) {
  const { el } = C;
  ul.replaceChildren(...(rows.length ? rows.map((r) => {
    const li = el("li", { className: r.success ? "" : "fail" });
    li.append(el("span", {}, C.fmtTime(r.ts)), el("span", {}, r.action + (r.success ? "" : " (failed)")),
      el("span", { className: "muted" }, showUser && r.user_id ? `user ${r.user_id.slice(0, 8)}` : ""));
    return li;
  }) : [el("li", { className: "muted" }, "No entries.")]));
}

// ---------------------------------------------------------------- team
export async function loadTeam(p) {
  const { $, el } = C;
  const ul = $("member-list");
  try {
    const members = await api(`/api/patients/${p.id}/members`);
    ul.replaceChildren(...members.map((m) => {
      const li = el("li");
      li.append(el("span", {}, `${m.full_name || m.email} · ${m.email}`), el("span", { className: `badge role-${m.role}` }, m.role));
      const me = C.state.user && m.user_id === C.state.user.id;
      if (m.role !== "owner" && (C.canDo("owner") || me)) {
        const b = el("button", { className: "btn ghost ack" }, me ? "Leave" : "Remove");
        b.addEventListener("click", async () => {
          if (!confirm(me ? "Leave this patient's care team?" : `Remove ${m.email} from the care team?`)) return;
          try {
            await api(`/api/patients/${p.id}/members/${m.user_id}`, { method: "DELETE" });
            if (me) await C.onLeftPatient(); else loadTeam(p);
          } catch (e) { C.toast(e.message); }
        });
        li.append(b);
      }
      return li;
    }));
  } catch (e) { C.toast(e.message); }
}

async function addMember(ev) {
  ev.preventDefault();
  const p = C.state.patient;
  const f = ev.target;
  try {
    await api(`/api/patients/${p.id}/members`, { method: "POST", body: { email: f.email.value.trim(), role: f.role.value } });
    f.reset(); C.toast("Shared."); loadTeam(p);
  } catch (e) { C.toast(e.message); }
}

// ---------------------------------------------------------------- settings
export async function loadSettings(p) {
  const f = C.$("form-settings");
  try {
    const s = await api(`/api/patients/${p.id}/alert-settings`);
    for (const k of ["pspi_moderate", "pspi_severe", "hr_high", "hr_low", "rr_high", "rr_low", "cooldown_s", "consecutive"]) {
      f.elements[k].value = s[k];
    }
    f.querySelectorAll("input[name=muted]").forEach((cb) => { cb.checked = s.muted.includes(cb.value); });
    const fresh = await api(`/api/patients/${p.id}`);
    C.$("baseline-status").textContent = fresh.baseline_updated_at
      ? `Calibrated ${C.fmtTime(fresh.baseline_updated_at)}.`
      : "Not calibrated yet — the next monitoring session calibrates automatically during the first ~20 s.";
  } catch (e) { C.toast(e.message); }
}

async function saveSettings(ev) {
  ev.preventDefault();
  const p = C.state.patient;
  const f = ev.target;
  const body = {};
  for (const k of ["pspi_moderate", "pspi_severe", "hr_high", "hr_low", "rr_high", "rr_low", "cooldown_s"]) body[k] = Number(f.elements[k].value);
  body.consecutive = parseInt(f.elements.consecutive.value, 10);
  body.muted = [...f.querySelectorAll("input[name=muted]:checked")].map((cb) => cb.value);
  try {
    await api(`/api/patients/${p.id}/alert-settings`, { method: "PUT", body });
    C.toast("Alarm settings saved.");
  } catch (e) { C.toast(e.message); }
}

async function resetBaseline() {
  const p = C.state.patient;
  if (!confirm("Discard the stored neutral-face baseline? The next session will recalibrate.")) return;
  try { await api(`/api/patients/${p.id}/baseline`, { method: "DELETE" }); loadSettings(p); } catch (e) { C.toast(e.message); }
}

// ---------------------------------------------------------------- account
export async function loadAccount() {
  const { $ } = C;
  const u = await C.refreshUser();
  $("mfa-status").textContent = u.totp_enabled
    ? "Enabled — an authenticator code is required at sign-in."
    : "Not enabled. Strongly recommended for accounts with access to patient data.";
  $("btn-mfa-setup").classList.toggle("hidden", u.totp_enabled);
  $("form-mfa-disable").classList.toggle("hidden", !u.totp_enabled);
  $("mfa-setup-box").classList.add("hidden");
  renderAudit($("my-audit"), await api("/api/auth/audit?limit=100").catch(() => []), false);
}

async function mfaSetup() {
  try {
    const r = await api("/api/auth/2fa/setup", { method: "POST" });
    C.$("mfa-secret").textContent = r.secret.replace(/(.{4})/g, "$1 ").trim();
    C.$("mfa-uri").textContent = r.otpauth_uri;
    C.$("mfa-setup-box").classList.remove("hidden");
    C.$("mfa-codes-box").classList.add("hidden");
  } catch (e) { C.toast(e.message); }
}

async function mfaEnable(ev) {
  ev.preventDefault();
  try {
    const r = await api("/api/auth/2fa/enable", { method: "POST", body: { code: ev.target.code.value.trim() } });
    C.$("mfa-codes").textContent = r.recovery_codes.join("\n");
    C.$("mfa-codes-box").classList.remove("hidden");
    C.$("mfa-setup-box").classList.add("hidden");
    ev.target.reset();
    // Enabling 2FA revokes all sessions (incl. this one) — the user signs in again with the code.
    clearToken();
    C.toast("2FA enabled. Save your recovery codes, then sign in again.", 10000);
    setTimeout(() => { if (confirm("Recovery codes saved? You will now be signed out.")) C.onSignedOut(); }, 500);
  } catch (e) { C.toast(e.message); }
}

async function mfaDisable(ev) {
  ev.preventDefault();
  const f = ev.target;
  try {
    await api("/api/auth/2fa/disable", { method: "POST", body: { password: f.password.value, code: f.code.value.trim() } });
    f.reset(); C.toast("2FA disabled."); loadAccount();
  } catch (e) { C.toast(e.message); }
}

async function changePassword(ev) {
  ev.preventDefault();
  const f = ev.target;
  try {
    await api("/api/auth/password", { method: "POST",
      body: { current_password: f.current_password.value, new_password: f.new_password.value } });
    f.reset(); clearToken();
    C.toast("Password changed — please sign in again.");
    C.onSignedOut();
  } catch (e) { C.toast(e.message); }
}

// ---------------------------------------------------------------- notifications
export async function notify(msg, patientName) {
  if (!("Notification" in window) || Notification.permission !== "granted" || !document.hidden) return;
  if (!["urgent", "concern"].includes(msg.level)) return;
  const title = `${msg.escalated ? "ESCALATED · " : ""}${msg.level.toUpperCase()} — ${patientName}`;
  const opts = { body: msg.reason, tag: msg.id, icon: "/static/icons/icon-192.png",
    requireInteraction: msg.level === "urgent", renotify: !!msg.escalated };
  try {
    const reg = navigator.serviceWorker ? await navigator.serviceWorker.getRegistration() : null;
    if (reg) await reg.showNotification(title, opts); else new Notification(title, opts);
  } catch (_) { /* notifications are best-effort */ }
}
