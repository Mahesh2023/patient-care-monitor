// Voice prosody features computed on-device — a 1:1 port of
// src/care_monitor/features/voice.py::extract_features. Ships ~7 floats/s
// instead of 32 KB/s of PCM.
const SR = 16000;

function resampleLinear(input, from, to) {
  if (from === to) return input;
  const ratio = from / to, n = Math.floor(input.length / ratio), out = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    const x = i * ratio, i0 = Math.floor(x), i1 = Math.min(i0 + 1, input.length - 1), f = x - i0;
    out[i] = input[i0] * (1 - f) + input[i1] * f;
  }
  return out;
}

// In-place iterative radix-2 FFT (length must be a power of two).
function fft(re, im) {
  const n = re.length;
  for (let i = 1, j = 0; i < n; i++) {
    let bit = n >> 1;
    for (; j & bit; bit >>= 1) j ^= bit;
    j ^= bit;
    if (i < j) { [re[i], re[j]] = [re[j], re[i]]; [im[i], im[j]] = [im[j], im[i]]; }
  }
  for (let len = 2; len <= n; len <<= 1) {
    const ang = (-2 * Math.PI) / len, wr = Math.cos(ang), wi = Math.sin(ang);
    for (let i = 0; i < n; i += len) {
      let cr = 1, ci = 0;
      for (let k = 0; k < len / 2; k++) {
        const a = i + k, b = a + len / 2;
        const tr = re[b] * cr - im[b] * ci, ti = re[b] * ci + im[b] * cr;
        re[b] = re[a] - tr; im[b] = im[a] - ti; re[a] += tr; im[a] += ti;
        const t = cr * wr - ci * wi; ci = cr * wi + ci * wr; cr = t;
      }
    }
  }
}

export function extractFeatures(audio, sr = SR) {
  const out = { pitch_mean: 0, pitch_std: 0, energy_mean: 0, energy_std: 0,
    spectral_centroid: 0, zero_crossing_rate: 0, duration_sec: audio.length / sr };
  if (audio.length < sr * 0.1) return out;
  let peak = 0;
  for (const v of audio) peak = Math.max(peak, Math.abs(v));
  const a = new Float32Array(audio.length);
  for (let i = 0; i < a.length; i++) a[i] = peak > 0 ? audio[i] / peak : 0;

  const frame = Math.floor(0.03 * sr), hop = Math.floor(0.01 * sr);
  const minLag = Math.floor(sr / 500), maxLag = Math.floor(sr / 50);
  const win = new Float32Array(frame);
  for (let i = 0; i < frame; i++) win[i] = 0.54 - 0.46 * Math.cos((2 * Math.PI * i) / (frame - 1));
  const w = new Float32Array(frame), pitches = [], energies = [];
  for (let s = 0; s + frame < a.length; s += hop) {
    let e = 0;
    for (let i = 0; i < frame; i++) { const v = a[s + i]; e += v * v; w[i] = v * win[i]; }
    energies.push(Math.sqrt(e / frame));
    let r0 = 0;
    for (let i = 0; i < frame; i++) r0 += w[i] * w[i];
    if (maxLag > frame) continue;  // mirrors numpy: corr length == frame
    let best = -Infinity, bestLag = 0;
    for (let lag = minLag; lag < maxLag; lag++) {
      let r = 0;
      for (let i = 0; i + lag < frame; i++) r += w[i] * w[i + lag];
      if (r > best) { best = r; bestLag = lag; }
    }
    if (best >= 0.3 * r0 && bestLag > 0) pitches.push(sr / bestLag);
  }
  const mean = (xs) => xs.reduce((p, c) => p + c, 0) / xs.length;
  const std = (xs, m) => Math.sqrt(xs.reduce((p, c) => p + (c - m) ** 2, 0) / xs.length);
  if (pitches.length) { out.pitch_mean = mean(pitches); out.pitch_std = std(pitches, out.pitch_mean); }
  if (energies.length) { out.energy_mean = mean(energies); out.energy_std = std(energies, out.energy_mean); }

  // Spectral centroid: magnitude-weighted mean frequency, accumulated over
  // up to 8 full-rate 1024-point FFT windows (≈ numpy full-length rfft).
  const N = 1024;
  let num = 0, den = 0;
  const nWin = Math.min(8, Math.floor(a.length / N));
  const hopW = nWin > 1 ? Math.floor((a.length - N) / (nWin - 1)) : 0;
  for (let wi = 0; wi < nWin; wi++) {
    const re = a.slice(wi * hopW, wi * hopW + N), im = new Float32Array(N);
    fft(re, im);
    for (let k = 0; k <= N / 2; k++) {
      const mag = Math.hypot(re[k], im[k]);
      num += ((k * sr) / N) * mag; den += mag;
    }
  }
  out.spectral_centroid = den > 1e-10 ? num / den : 0;

  let zc = 0;
  for (let i = 1; i < a.length; i++) if (Math.sign(a[i]) !== Math.sign(a[i - 1])) zc++;
  out.zero_crossing_rate = zc / a.length;
  for (const k of Object.keys(out)) out[k] = Math.round(out[k] * 1e4) / 1e4;
  return out;
}

export class VoiceTap {
  constructor(stream, onFeatures) {
    this.stream = stream;
    this.onFeatures = onFeatures;
    this.ctx = null;
    this.buf = []; this.len = 0;
  }

  async start() {
    this.ctx = new AudioContext();
    await this.ctx.audioWorklet.addModule("/static/js/audio-worklet.js");
    const src = this.ctx.createMediaStreamSource(this.stream);
    this.node = new AudioWorkletNode(this.ctx, "care-tap");
    const chunk = Math.round(this.ctx.sampleRate);  // 1 s windows
    this.node.port.onmessage = (ev) => {
      this.buf.push(ev.data); this.len += ev.data.length;
      if (this.len >= chunk) {
        const merged = new Float32Array(this.len);
        let o = 0;
        for (const b of this.buf) { merged.set(b, o); o += b.length; }
        this.buf = []; this.len = 0;
        this.onFeatures(extractFeatures(resampleLinear(merged, this.ctx.sampleRate, SR)));
      }
    };
    src.connect(this.node);  // worklet need not reach destination (no echo)
  }

  async stop() {
    try { this.node && this.node.disconnect(); } catch (_) { /* noop */ }
    if (this.ctx) await this.ctx.close().catch(() => {});
    this.ctx = null;
  }
}
