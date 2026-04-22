"""Embedded single-page dashboard.

HTML + CSS + JS are kept in one Python string so the whole app ships as
one Docker layer with no static-file-serving surprises on Render / Railway /
Fly.io (we learned this the hard way).
"""
DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>CARE-MM · Patient Care Monitor</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
:root {
  --bg-0: #0b1020;
  --bg-1: #121a33;
  --bg-2: #1b2445;
  --border: rgba(124,140,200,.18);
  --text: #e6ecff;
  --muted: #8a96bd;
  --accent: #6366f1;
  --accent-2: #8b5cf6;
  --ok: #10b981;
  --warn: #f59e0b;
  --bad: #ef4444;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body { height: 100%; }
body {
  font-family: 'Inter', system-ui, -apple-system, sans-serif;
  background: radial-gradient(1200px 600px at 0% 0%, #1a2350 0%, var(--bg-0) 50%);
  color: var(--text);
  min-height: 100vh;
}
.top {
  display: flex; align-items: center; justify-content: space-between;
  padding: 18px 28px; border-bottom: 1px solid var(--border);
  backdrop-filter: blur(8px); position: sticky; top: 0; z-index: 20;
  background: rgba(11,16,32,.75);
}
.brand { display:flex; align-items:center; gap:12px; }
.brand .logo {
  width:36px; height:36px; border-radius:10px;
  background: linear-gradient(135deg,var(--accent),var(--accent-2));
  display:flex; align-items:center; justify-content:center; font-weight:700;
}
.brand h1 { font-size: 18px; font-weight: 600; letter-spacing: -.01em; }
.brand .tag { color: var(--muted); font-size:12px; }
.pill {
  padding:6px 12px; border-radius: 999px; font-size:12px; font-weight:500;
  border:1px solid var(--border); color: var(--muted);
}
.pill.ok { color: var(--ok); border-color: rgba(16,185,129,.4); background: rgba(16,185,129,.1); }
.pill.bad { color: var(--bad); border-color: rgba(239,68,68,.4); background: rgba(239,68,68,.1); }

.grid {
  display:grid; gap:18px; padding: 24px 28px;
  grid-template-columns: 380px 1fr;
}
@media (max-width: 960px) { .grid { grid-template-columns: 1fr; } }
.card {
  background: linear-gradient(180deg, var(--bg-1), var(--bg-2));
  border: 1px solid var(--border); border-radius: 14px;
  padding: 18px; box-shadow: 0 12px 30px rgba(0,0,0,.25);
}
.card h2 { font-size: 13px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing:.08em; margin-bottom: 12px; }
.video-wrap { position:relative; border-radius:12px; overflow:hidden; aspect-ratio: 4/3; background:#000; }
video, canvas.overlay { position:absolute; inset:0; width:100%; height:100%; object-fit:cover; }
canvas.overlay { pointer-events:none; }
.consent {
  background: rgba(99,102,241,.1); border:1px solid rgba(99,102,241,.3);
  border-radius: 12px; padding: 14px; margin-bottom: 14px; font-size: 13px; color: var(--text);
}
.consent b { color: #fff; }
.row { display:flex; gap:10px; flex-wrap: wrap; }
button {
  background: linear-gradient(135deg,var(--accent),var(--accent-2));
  color:white; border:0; padding: 10px 16px; border-radius: 10px;
  font-weight: 600; cursor: pointer; transition: transform .12s, box-shadow .12s;
}
button:hover { transform: translateY(-1px); box-shadow: 0 8px 20px rgba(99,102,241,.35); }
button.ghost { background: transparent; border: 1px solid var(--border); color: var(--text); }
button:disabled { opacity:.5; cursor: not-allowed; transform: none; box-shadow: none; }

.metrics {
  display:grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap: 12px;
}
.metric {
  background: rgba(255,255,255,.02); border:1px solid var(--border);
  border-radius:10px; padding: 12px;
}
.metric .label { font-size:11px; text-transform:uppercase; color: var(--muted); letter-spacing:.08em; }
.metric .val { font-size: 26px; font-weight:700; margin-top: 6px; letter-spacing:-.02em; }
.metric .sub { font-size:11px; color: var(--muted); margin-top: 2px; }

.bars { display:flex; flex-direction: column; gap: 6px; max-height: 220px; overflow-y: auto; padding-right: 4px; }
.bar { display:flex; align-items:center; gap:8px; font-size:12px; }
.bar .name { width: 44px; color: var(--muted); font-family: ui-monospace, monospace; }
.bar .track { flex:1; height:8px; background: rgba(255,255,255,.06); border-radius: 4px; overflow:hidden; }
.bar .fill { height:100%; background: linear-gradient(90deg,var(--accent),var(--accent-2)); transition: width .18s; }
.bar .v { width: 38px; text-align:right; color: var(--text); font-variant-numeric: tabular-nums; }

.tag-chip {
  display:inline-block; background: rgba(139,92,246,.15); color: #c4b5fd;
  border:1px solid rgba(139,92,246,.35); padding: 4px 10px; border-radius: 999px;
  font-size: 12px; font-weight: 500;
}
.level-normal    { color: var(--ok);   border-color: rgba(16,185,129,.4);  background: rgba(16,185,129,.1); }
.level-attention { color: #a5b4fc;     border-color: rgba(165,180,252,.4); background: rgba(165,180,252,.1); }
.level-concern   { color: var(--warn); border-color: rgba(245,158,11,.4);  background: rgba(245,158,11,.1); }
.level-urgent    { color: var(--bad);  border-color: rgba(239,68,68,.4);   background: rgba(239,68,68,.1); }

.alert-feed { display:flex; flex-direction:column; gap:8px; max-height: 260px; overflow-y:auto; }
.alert {
  background: rgba(255,255,255,.02); border:1px solid var(--border);
  border-radius:10px; padding: 10px 12px;
}
.alert .hdr { display:flex; justify-content:space-between; align-items:center; gap:8px; font-size:12px; color: var(--muted); }
.alert .reason { font-size:13px; margin-top:4px; }

.llm-card {
  background: linear-gradient(135deg, rgba(99,102,241,.12), rgba(139,92,246,.12));
  border: 1px solid rgba(139,92,246,.35); border-radius:12px; padding: 14px;
  font-size: 14px; line-height: 1.55; min-height: 70px;
}
.llm-card .label { color: #c4b5fd; font-size:11px; text-transform: uppercase; letter-spacing:.08em; margin-bottom: 6px; }

.footer { color: var(--muted); font-size:11px; padding: 18px 28px 28px; text-align: center; }
.footer a { color: var(--muted); }

.chart-wrap { height: 180px; }
</style>
</head>
<body>

<div class="top">
  <div class="brand">
    <div class="logo">❤</div>
    <div>
      <h1>CARE-MM — Patient Care Monitor</h1>
      <div class="tag">FACS-grounded · LLM-augmented · research/educational use only</div>
    </div>
  </div>
  <div class="row">
    <span class="pill" id="status">disconnected</span>
    <span class="pill" id="fps">0 fps</span>
  </div>
</div>

<div class="grid">
  <!-- LEFT: video + controls -->
  <div>
    <div class="card">
      <h2>Live Camera</h2>
      <div class="consent" id="consentBox">
        <b>⚠ Consent required.</b> This tool analyses facial video to estimate pain, comfort,
        and distress signals for non-verbal patients. <b>No raw video is stored.</b> By clicking
        <b>Grant Consent & Start</b> you confirm you have permission to monitor this individual and
        understand this is <b>not a medical device</b>.
      </div>
      <div class="video-wrap">
        <video id="video" autoplay playsinline muted></video>
        <canvas id="overlay" class="overlay"></canvas>
      </div>
      <div class="row" style="margin-top:12px;">
        <button id="startBtn">Grant Consent &amp; Start</button>
        <button id="stopBtn" class="ghost" disabled>Stop &amp; Revoke</button>
      </div>
    </div>

    <div class="card" style="margin-top:18px;">
      <h2>Behavioural Tag</h2>
      <div id="tag"><span class="tag-chip">waiting</span></div>
      <div style="margin-top:8px; color: var(--muted); font-size:12px;" id="obs">observations will appear here</div>
    </div>

    <div class="card" style="margin-top:18px;">
      <h2>Clinical Summary (LLM)</h2>
      <div class="llm-card">
        <div class="label">Hedged, FACS-cited · Groq Llama-3.3 or local Ollama</div>
        <div id="llm">—</div>
      </div>
    </div>
  </div>

  <!-- RIGHT: signals -->
  <div>
    <div class="card">
      <h2>Vitals &amp; Pain</h2>
      <div class="metrics">
        <div class="metric">
          <div class="label">PSPI (0-16)</div>
          <div class="val" id="pspi">0.0</div>
          <div class="sub" id="painLevel">—</div>
        </div>
        <div class="metric">
          <div class="label">Heart Rate (rPPG)</div>
          <div class="val" id="hr">—</div>
          <div class="sub" id="hrQuality">no_signal</div>
        </div>
        <div class="metric">
          <div class="label">Comfort</div>
          <div class="val" id="comfort">0.5</div>
          <div class="sub">0 = distress, 1 = ease</div>
        </div>
        <div class="metric">
          <div class="label">Arousal</div>
          <div class="val" id="arousal">0.5</div>
          <div class="sub">0 = flat, 1 = agitated</div>
        </div>
      </div>
      <div class="chart-wrap" style="margin-top:14px;"><canvas id="trendChart"></canvas></div>
    </div>

    <div class="card" style="margin-top:18px;">
      <h2>Active Action Units (FACS)</h2>
      <div class="bars" id="auBars"></div>
    </div>

    <div class="card" style="margin-top:18px;">
      <h2>Alerts</h2>
      <div class="alert-feed" id="alerts">
        <div class="alert"><div class="hdr"><span>waiting</span><span>—</span></div>
        <div class="reason">no alerts yet.</div></div>
      </div>
    </div>
  </div>
</div>

<div class="footer">
  CARE-MM v2.0 · Not FDA-approved · Not a medical device ·
  <a href="/docs">API docs</a> · <a href="/health">health</a> · <a href="/metrics">metrics</a>
</div>

<script>
const AU_DESC = {
  AU1:"inner brow raise", AU2:"outer brow raise", AU4:"brow furrow",
  AU5:"upper lid raise", AU6:"cheek raise", AU7:"lid tighten",
  AU9:"nose wrinkle", AU10:"upper lip raise", AU12:"lip-corner pull (smile)",
  AU14:"dimple", AU15:"lip-corner depress", AU17:"chin raise",
  AU20:"lip stretch", AU23:"lip tighten", AU24:"lip pucker",
  AU25:"lips part", AU26:"jaw drop", AU28:"lip roll",
  AU43:"eyes closed", AU45:"blink",
};

const $ = (id) => document.getElementById(id);
const state = { session_id:null, ws:null, stream:null, sending:false, lastSent:0 };

const trendData = {
  labels: [],
  datasets: [
    { label:"PSPI/16", data:[], borderColor:"#ef4444", backgroundColor:"rgba(239,68,68,.15)", tension:.3, borderWidth:2, pointRadius:0 },
    { label:"Comfort", data:[], borderColor:"#10b981", backgroundColor:"rgba(16,185,129,.12)", tension:.3, borderWidth:2, pointRadius:0 },
    { label:"Arousal", data:[], borderColor:"#6366f1", backgroundColor:"rgba(99,102,241,.12)", tension:.3, borderWidth:2, pointRadius:0 },
  ],
};
const trendChart = new Chart($("trendChart").getContext("2d"), {
  type:"line", data: trendData,
  options: {
    animation:false, responsive:true, maintainAspectRatio:false,
    scales: {
      x:{ ticks:{color:"#8a96bd",maxTicksLimit:6},grid:{color:"rgba(255,255,255,.06)"} },
      y:{ min:0, max:1, ticks:{color:"#8a96bd"}, grid:{color:"rgba(255,255,255,.06)"} }
    },
    plugins:{ legend:{ labels:{color:"#e6ecff"} } }
  },
});

async function grantConsent() {
  const r = await fetch("/api/consent", {
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body: JSON.stringify({purpose:"clinical_monitoring"})
  });
  const j = await r.json();
  state.session_id = j.session_id;
  return j.session_id;
}

async function revokeConsent() {
  if (!state.session_id) return;
  await fetch("/api/consent/revoke",{
    method:"POST", headers:{"Content-Type":"application/json"},
    body: JSON.stringify({session_id: state.session_id})
  });
}

function connectWS(sid) {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const url = `${proto}://${location.host}/ws?session_id=${encodeURIComponent(sid)}`;
  const ws = new WebSocket(url);
  ws.onopen = () => { $("status").textContent = "connected"; $("status").classList.add("ok"); };
  ws.onclose = () => { $("status").textContent = "disconnected"; $("status").classList.remove("ok"); };
  ws.onerror = () => { $("status").textContent = "error"; $("status").classList.add("bad"); };
  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.type === "frame") render(msg.data);
    else if (msg.type === "error") { $("status").textContent = msg.code || "error"; $("status").classList.add("bad"); }
  };
  return ws;
}

async function startCamera() {
  const v = $("video");
  state.stream = await navigator.mediaDevices.getUserMedia({video:{width:{ideal:480},height:{ideal:360}},audio:false});
  v.srcObject = state.stream;
}

async function streamLoop() {
  const v = $("video");
  const c = document.createElement("canvas");
  c.width = 320; c.height = 240;
  const ctx = c.getContext("2d");
  const fpsTarget = 8;
  while (state.sending) {
    if (v.readyState >= 2 && state.ws && state.ws.readyState === WebSocket.OPEN) {
      ctx.drawImage(v, 0, 0, c.width, c.height);
      const jpg = c.toDataURL("image/jpeg", 0.6).split(",")[1];
      try { state.ws.send(JSON.stringify({frame: jpg, ts: Date.now()})); } catch(e) {}
    }
    await new Promise(r => setTimeout(r, 1000 / fpsTarget));
  }
}

function setLevelClass(el, level) {
  el.classList.remove("level-normal","level-attention","level-concern","level-urgent");
  el.classList.add("level-" + (level || "normal"));
}

function render(d) {
  $("fps").textContent = (d.fps || 0).toFixed(1) + " fps";
  if (!d.face_detected) {
    $("tag").innerHTML = `<span class="tag-chip">no face detected</span>`;
    return;
  }

  // Metrics
  const pspi = (d.pain && d.pain.pspi) || 0;
  $("pspi").textContent = pspi.toFixed(2);
  $("painLevel").textContent = (d.pain && d.pain.level) || "—";

  if (d.heart_rate && d.heart_rate.bpm) {
    $("hr").textContent = d.heart_rate.bpm.toFixed(0) + " bpm";
    $("hrQuality").textContent = d.heart_rate.quality;
  } else {
    $("hr").textContent = "—";
    $("hrQuality").textContent = "no_signal";
  }

  $("comfort").textContent = (d.distress.comfort).toFixed(2);
  $("arousal").textContent = (d.distress.arousal).toFixed(2);

  // Behavioural tag
  const tagEl = $("tag");
  tagEl.innerHTML = `<span class="tag-chip">${d.distress.tag}</span>
    <span class="tag-chip" style="margin-left:6px;">conf ${d.distress.confidence.toFixed(2)}</span>`;
  $("obs").textContent = (d.distress.observations||[]).join(" · ") || "no notable observations";

  // AU bars
  const entries = Object.entries(d.action_units || {}).filter(([,v]) => v > 0.05)
    .sort((a,b)=>b[1]-a[1]).slice(0,10);
  $("auBars").innerHTML = entries.map(([k,v]) => `
    <div class="bar" title="${AU_DESC[k]||""}">
      <div class="name">${k}</div>
      <div class="track"><div class="fill" style="width:${Math.min(100,v*100).toFixed(0)}%"></div></div>
      <div class="v">${v.toFixed(2)}</div>
    </div>`).join("") || `<div style="color:var(--muted);font-size:12px;">no AU above 0.05</div>`;

  // Alerts (append new)
  if (d.alerts && d.alerts.length) {
    const feed = $("alerts");
    for (const a of d.alerts) {
      const el = document.createElement("div");
      el.className = "alert";
      el.innerHTML = `
        <div class="hdr">
          <span class="tag-chip level-${a.level}">${a.level.toUpperCase()} · ${a.key}</span>
          <span>${new Date(a.ts*1000).toLocaleTimeString()}</span>
        </div>
        <div class="reason">${a.reason}</div>`;
      feed.prepend(el);
    }
    while (feed.children.length > 20) feed.removeChild(feed.lastChild);
  }

  // LLM
  if (d.clinical_summary) $("llm").textContent = d.clinical_summary;

  // Trend
  const t = new Date().toLocaleTimeString().split(" ")[0];
  trendData.labels.push(t);
  trendData.datasets[0].data.push(Math.min(1, pspi/16));
  trendData.datasets[1].data.push(d.distress.comfort);
  trendData.datasets[2].data.push(d.distress.arousal);
  if (trendData.labels.length > 60) {
    trendData.labels.shift();
    trendData.datasets.forEach(ds => ds.data.shift());
  }
  trendChart.update("none");
}

$("startBtn").onclick = async () => {
  try {
    $("startBtn").disabled = true;
    const sid = await grantConsent();
    await startCamera();
    state.ws = connectWS(sid);
    state.sending = true;
    streamLoop();
    $("stopBtn").disabled = false;
  } catch (e) {
    alert("Camera / consent failed: " + e.message);
    $("startBtn").disabled = false;
  }
};
$("stopBtn").onclick = async () => {
  state.sending = false;
  if (state.ws) state.ws.close();
  if (state.stream) state.stream.getTracks().forEach(t => t.stop());
  await revokeConsent();
  $("startBtn").disabled = false;
  $("stopBtn").disabled = true;
  $("status").textContent = "revoked";
};
</script>
</body>
</html>
"""
