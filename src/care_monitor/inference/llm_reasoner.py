"""Clinical LLM reasoning layer (Groq OpenAI-compatible API / local Ollama).

Produces a single-sentence, hedged, FACS-cited summary for caregivers —
**never** a diagnosis. Implements the hybrid "rules + LLM" pattern
(Sălăgean, Leba & Ionica 2025, *Applied Sciences* 15(12):6417) by grounding
the LLM in the AU evidence.

Production properties:
  * fully async (shared `httpx.AsyncClient`), never blocks the event loop;
  * per-process concurrency cap (semaphore) so a traffic spike cannot fan out
    into thousands of simultaneous upstream calls;
  * circuit breaker: after N consecutive failures, calls are skipped for a
    cool-off period (degrades gracefully to rules-only output);
  * per-session cooldown is enforced by the caller (`SessionPipeline`).
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Optional

import httpx

from ..config import settings
from ..logging_utils import get_logger

log = get_logger(__name__)


SYSTEM_PROMPT = """You are a clinical affective-computing assistant advising a
caregiver who is remotely monitoring a non-verbal or communication-impaired
patient (e.g., dementia, ICU-intubated, pediatric, post-stroke aphasia).

You are given:
  - FACS Action Unit intensities (from MediaPipe blendshapes)
  - Head pose / gaze / blink rate
  - PSPI pain score (Prkachin & Solomon 1992; 0-16 scale)
  - Heart rate (from rPPG; may be noisy)
  - Optional voice prosody state and caregiver-note sentiment
  - Rule-based behavioural tag and short observation list

TASK: produce ONE short hedged clinical-observation sentence (< 25 words)
that a caregiver can act on. Follow ALL of these rules:
  1. Start with "STATE:" exactly.
  2. Use hedging words: "possibly", "may", "appears", "consistent with".
  3. Cite at least one AU (e.g., "AU4", "AU6+AU12") or rPPG or PSPI.
  4. DO NOT output a diagnosis. DO NOT claim to "detect emotions".
  5. If PSPI >= 4 or severe pain level, recommend caregiver check-in.
  6. If no salient signals, say exactly: "STATE: No salient distress signals observed."
"""


def build_user_prompt(snapshot: dict) -> str:
    aus = {k: round(v, 2) for k, v in snapshot.get("aus", {}).items() if v > 0.15}
    return (
        f"AUs (0-1): {json.dumps(aus)}\n"
        f"Head pose (deg): {json.dumps({k: round(v, 1) for k, v in snapshot.get('head_pose', {}).items()})}\n"
        f"Gaze averted: {bool(snapshot.get('gaze', {}).get('averted', False))}\n"
        f"Blink/min: {snapshot.get('blink_rpm', 0.0):.1f}\n"
        f"PSPI: {snapshot.get('pspi', 0.0):.2f}  ({snapshot.get('pain_level', 'none')})\n"
        f"rPPG HR: {snapshot.get('hr_bpm', 0.0):.0f} bpm  (quality={snapshot.get('hr_quality', 'no_signal')})\n"
        f"Voice: {snapshot.get('voice_state')}  Note pain/distress terms: "
        f"{snapshot.get('text_pain')}/{snapshot.get('text_distress')}\n"
        f"Behavioural tag: {snapshot.get('tag', 'neutral')}\n"
        f"Observations: {snapshot.get('observations', [])[:8]}\n"
        f"Recent micro-events: {list(snapshot.get('micro_events', []))[-3:]}\n\n"
        f"Give ONE sentence starting with STATE:"
    )


class _CircuitBreaker:
    def __init__(self, threshold: int = 5, cooloff_s: float = 60.0) -> None:
        self.threshold = threshold
        self.cooloff_s = cooloff_s
        self.failures = 0
        self.open_until = 0.0

    def allow(self) -> bool:
        return time.monotonic() >= self.open_until

    def success(self) -> None:
        self.failures = 0

    def failure(self) -> None:
        self.failures += 1
        if self.failures >= self.threshold:
            self.open_until = time.monotonic() + self.cooloff_s
            self.failures = 0
            log.warning("LLM circuit opened for %.0fs", self.cooloff_s)


class LLMReasoner:
    """Process-wide singleton (see `get_reasoner`)."""

    def __init__(self) -> None:
        self.provider = settings.llm_provider.lower()
        self.model = settings.llm_model
        self._client: Optional[httpx.AsyncClient] = None
        self._sem = asyncio.Semaphore(max(1, settings.llm_max_concurrency))
        self._breaker = _CircuitBreaker()
        if not settings.enable_llm_reasoning or self.provider == "none":
            self.provider = "none"
        elif self.provider == "groq" and not settings.groq_api_key:
            log.warning("GROQ_API_KEY missing — LLM reasoning disabled.")
            self.provider = "none"
        if self.provider != "none":
            log.info("LLM reasoner configured: %s / %s", self.provider, self.model)

    def available(self) -> bool:
        return self.provider != "none"

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=settings.llm_timeout_seconds,
                limits=httpx.Limits(max_connections=settings.llm_max_concurrency * 2),
            )
        return self._client

    async def reason(self, snapshot: dict) -> str:
        if not self.available() or not self._breaker.allow():
            return ""
        if self._sem.locked():
            return ""  # saturated: skip rather than queue (summaries are best-effort)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(snapshot)},
        ]
        async with self._sem:
            try:
                if self.provider == "groq":
                    r = await self._http().post(
                        f"{settings.groq_base_url}/chat/completions",
                        headers={"Authorization": f"Bearer {settings.groq_api_key}"},
                        json={"model": self.model, "messages": messages,
                              "max_tokens": 80, "temperature": 0.2},
                    )
                    r.raise_for_status()
                    text = r.json()["choices"][0]["message"]["content"].strip()
                else:
                    r = await self._http().post(
                        f"{settings.ollama_host}/api/chat",
                        json={"model": self.model, "messages": messages, "stream": False,
                              "options": {"temperature": 0.2, "num_predict": 80}},
                    )
                    r.raise_for_status()
                    text = r.json()["message"]["content"].strip()
            except Exception as e:
                self._breaker.failure()
                log.warning("LLM call failed: %s", type(e).__name__)
                return ""
        self._breaker.success()
        text = text.splitlines()[0][:300] if text else ""
        if text and not text.startswith("STATE:"):
            text = f"STATE: {text}"
        return text

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


_reasoner: Optional[LLMReasoner] = None


def get_reasoner() -> LLMReasoner:
    global _reasoner
    if _reasoner is None:
        _reasoner = LLMReasoner()
    return _reasoner
