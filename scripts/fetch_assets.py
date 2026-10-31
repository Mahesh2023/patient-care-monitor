"""Download pinned, hash-verified frontend assets into app/static/vendor.

Self-hosting MediaPipe Tasks-Vision (WASM), Chart.js and the face model means
the browser never loads third-party code at runtime (strict CSP: 'self'), and
a CDN compromise cannot inject code. Run at Docker build time and once locally:

    python scripts/fetch_assets.py
"""
from __future__ import annotations

import hashlib
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "app" / "static" / "vendor"
MP = "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@1.1.1"

ASSETS = {
    "mediapipe/vision_bundle.mjs": (
        f"{MP}/vision_bundle.mjs",
        "a84921e02321e582484c1f8126d344b5f33b791fa09c640a52e20ee8632068f1"),
    "mediapipe/wasm/vision_wasm_internal.js": (
        f"{MP}/wasm/vision_wasm_internal.js",
        "6522286aa32dd93eff17c3da002b0649516f87abfec7a80b5bfe5c9625caa5f8"),
    "mediapipe/wasm/vision_wasm_internal.wasm": (
        f"{MP}/wasm/vision_wasm_internal.wasm",
        "0e101a010e262ef8e78f22e3c95b60a9705fd06962753c9acd6356d9fb56b7bd"),
    "mediapipe/wasm/vision_wasm_nosimd_internal.js": (
        f"{MP}/wasm/vision_wasm_nosimd_internal.js",
        "942654dbdcebce08ea039af23d18e58bebf23c8607d74023d2df7071c8a7b638"),
    "mediapipe/wasm/vision_wasm_nosimd_internal.wasm": (
        f"{MP}/wasm/vision_wasm_nosimd_internal.wasm",
        "c9b1b69bb87baf9e529254d8559dcbcf4c5a9c0eda84f56a12f17d675335ec9c"),
    "chart.umd.min.js": (
        "https://cdn.jsdelivr.net/npm/chart.js@4.5.1/dist/chart.umd.min.js",
        "48444a82d4edcb5bec0f1965faacdde18d9c17db3063d042abada2f705c9f54a"),
    "models/face_landmarker.task": (
        "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task",
        "64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff"),
}


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    for rel, (url, digest) in ASSETS.items():
        dest = ROOT / rel
        if dest.exists() and sha256(dest) == digest:
            print(f"ok      {rel}")
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        print(f"fetch   {rel}")
        urllib.request.urlretrieve(url, tmp)
        got = sha256(tmp)
        if got != digest:
            tmp.unlink(missing_ok=True)
            print(f"HASH MISMATCH for {rel}: {got}", file=sys.stderr)
            return 1
        tmp.replace(dest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
