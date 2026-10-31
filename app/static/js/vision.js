// On-device face perception (MediaPipe Tasks-Vision WASM, self-hosted).
// Produces the compact numeric sample defined by the server handshake:
//   { t, bs[], m[16], lm[], rgb[3] }  — no pixels ever leave the browser.
import { FaceLandmarker, FilesetResolver } from "/static/vendor/mediapipe/vision_bundle.mjs";

const WASM_BASE = "/static/vendor/mediapipe/wasm";
const MODEL = "/static/vendor/models/face_landmarker.task";
const R4 = (v) => Math.round(v * 1e4) / 1e4;

export async function createLandmarker() {
  const fileset = await FilesetResolver.forVisionTasks(WASM_BASE);
  let lastErr;
  for (const delegate of ["GPU", "CPU"]) {
    try {
      const lm = await FaceLandmarker.createFromOptions(fileset, {
        baseOptions: { modelAssetPath: MODEL, delegate },
        runningMode: "VIDEO",
        numFaces: 1,
        outputFaceBlendshapes: true,
        outputFacialTransformationMatrixes: true,
        minFaceDetectionConfidence: 0.5,
        minFacePresenceConfidence: 0.5,
        minTrackingConfidence: 0.5,
      });
      return { landmarker: lm, delegate };
    } catch (e) { lastErr = e; }
  }
  throw lastErr;
}

export class FeatureExtractor {
  constructor(landmarker, contract, canvas) {
    this.lm = landmarker;
    this.contract = contract;
    this.canvas = canvas;
    this.canvas.width = 160;
    this.canvas.height = 120;
    this.ctx = canvas.getContext("2d", { willReadFrequently: true });
    this.lastTs = 0;
  }

  _foreheadRGB(video, pts) {
    const W = this.canvas.width, H = this.canvas.height;
    let x0 = 1, y0 = 1, x1 = 0, y1 = 0;
    for (const i of this.contract.forehead_landmarks) {
      const p = pts[i]; if (!p) continue;
      x0 = Math.min(x0, p.x); y0 = Math.min(y0, p.y); x1 = Math.max(x1, p.x); y1 = Math.max(y1, p.y);
    }
    const bx = Math.max(0, Math.floor(x0 * W)), by = Math.max(0, Math.floor(y0 * H));
    const bw = Math.min(W - bx, Math.ceil((x1 - x0) * W)), bh = Math.min(H - by, Math.ceil((y1 - y0) * H));
    if (bw < 3 || bh < 2) return null;
    this.ctx.drawImage(video, 0, 0, W, H);
    const d = this.ctx.getImageData(bx, by, bw, bh).data;
    let r = 0, g = 0, b = 0;
    const n = d.length / 4;
    for (let i = 0; i < d.length; i += 4) { r += d[i]; g += d[i + 1]; b += d[i + 2]; }
    return [R4(r / n), R4(g / n), R4(b / n)];
  }

  /** Analyse the current video frame; returns a wire sample. */
  extract(video) {
    let ts = performance.now();
    if (ts <= this.lastTs) ts = this.lastTs + 1;  // MediaPipe needs strictly increasing ts
    this.lastTs = ts;
    const res = this.lm.detectForVideo(video, ts);
    const sample = { t: Date.now(), bs: null, m: null, lm: null, rgb: null };
    const pts = res.faceLandmarks && res.faceLandmarks[0];
    if (!pts) return sample;

    const cats = (res.faceBlendshapes && res.faceBlendshapes[0] && res.faceBlendshapes[0].categories) || [];
    const map = Object.create(null);
    for (const c of cats) map[c.categoryName] = c.score;
    sample.bs = this.contract.blendshapes.map((n) => R4(Math.min(1, Math.max(0, map[n] || 0))));

    const mat = res.facialTransformationMatrixes && res.facialTransformationMatrixes[0];
    if (mat && mat.data && mat.data.length === 16) sample.m = Array.from(mat.data, R4);

    const lm = [];
    for (const i of this.contract.gaze_landmarks) {
      const p = pts[i];
      if (!p) { lm.length = 0; break; }
      lm.push(R4(p.x), R4(p.y));
    }
    if (lm.length === this.contract.gaze_landmarks.length * 2) sample.lm = lm;

    sample.rgb = this._foreheadRGB(video, pts);
    return sample;
  }

  close() { try { this.lm.close(); } catch (_) { /* noop */ } }
}
