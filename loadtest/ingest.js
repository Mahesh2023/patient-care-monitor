// k6 load test: simulates N concurrent monitoring streams (browser-side
// inference already done) sending 2 batches/s of 5 samples each.
//
//   k6 run -e BASE=https://care-mm.onrender.com -e VUS=200 -e DURATION=5m loadtest/ingest.js
//
// Each VU registers its own account, creates a patient + consented session,
// then streams. Watch p95 `ws_result_latency` and server CPU to size
// instances (streams per instance = VUS / instances at target CPU ~60%).
import http from "k6/http";
import ws from "k6/ws";
import { check } from "k6";
import { Trend, Counter } from "k6/metrics";

const BASE = __ENV.BASE || "http://localhost:8000";
const WS_BASE = BASE.replace(/^http/, "ws");
const VUS = parseInt(__ENV.VUS || "50", 10);
const DURATION = __ENV.DURATION || "2m";

export const options = {
  scenarios: { streams: { executor: "constant-vus", vus: VUS, duration: DURATION } },
  thresholds: { ws_result_latency: ["p(95)<250"], ws_errors: ["count<10"] },
};

const latency = new Trend("ws_result_latency", true);
const errors = new Counter("ws_errors");
const NAMES = JSON.parse(open("./blendshapes.json"));

function sample(t, pain) {
  const bs = NAMES.map((n) => (pain && /browDown|eyeSquint|noseSneer/.test(n) ? 0.4 : Math.random() * 0.1));
  return { t, bs, m: [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1],
    lm: Array.from({ length: 28 }, (_, i) => 0.3 + (i % 5) * 0.05),
    rgb: [120, 100 + Math.sin(t / 130) * 2, 90] };
}

export default function () {
  const email = `load-${__VU}-${Date.now()}@example.com`;
  const J = { headers: { "Content-Type": "application/json" } };
  const reg = http.post(`${BASE}/api/auth/register`, JSON.stringify({ email, password: "load-test-password-1" }), J);
  if (!check(reg, { registered: (r) => r.status === 201 })) { errors.add(1); return; }
  const H = { headers: { "Content-Type": "application/json", Authorization: `Bearer ${reg.json("access_token")}` } };
  const p = http.post(`${BASE}/api/patients`, JSON.stringify({ display_name: `p${__VU}` }), H).json();
  const s = http.post(`${BASE}/api/sessions`, JSON.stringify({ patient_id: p.id, consent_confirmed: true }), H).json();

  ws.connect(`${WS_BASE}${s.ws_path}?ticket=${s.ws_ticket}`, {}, (sock) => {
    let sentAt = 0;
    sock.on("message", (raw) => {
      const msg = JSON.parse(raw);
      if (msg.type === "result" && sentAt) latency.add(Date.now() - sentAt);
      if (msg.type === "error") errors.add(1);
    });
    sock.on("error", () => errors.add(1));
    sock.setInterval(() => {
      const t0 = Date.now();
      const pain = Math.random() < 0.05;
      sentAt = t0;
      sock.send(JSON.stringify({ type: "batch", samples: [0, 100, 200, 300, 400].map((d) => sample(t0 - 400 + d, pain)) }));
    }, 500);
    sock.setTimeout(() => sock.close(), 60000);
  });
}
