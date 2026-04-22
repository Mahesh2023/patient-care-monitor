"""Clinical LLM reasoning layer (Groq Llama-3.3-70B free tier / local Ollama).

Produces a single-sentence, hedged, FACS-cited summary for caregivers —
**never** a diagnosis. Implements the hybrid "rules + LLM" pattern that
Sălăgean, Leba & Ionica (2025, *Applied Sciences* 15(12):6417) showed
achieves 93.3% on CASME II by grounding the LLM in the AU evidence.

Prompt constraints:
  * output must start with "STATE:"
  * output must use hedging words (possibly / appears / may)
  * output must cite at least one AU by number
"""
from __future__ import annotations
import json
import time
from typing import Dict, List, Optional

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


def _build_user_prompt(snapshot: Dict) -> str:
    return (
        f"AUs (0-1): {json.dumps({k: round(v, 2) for k, v in snapshot['aus'].items() if v > 0.15})}\n"
        f"Head pose (deg): {json.dumps({k: round(v, 1) for k, v in snapshot['head_pose'].items()})}\n"
        f"Gaze: {json.dumps(snapshot['gaze'])}\n"
        f"Blink/min: {snapshot['blink_rpm']:.1f}\n"
        f"PSPI: {snapshot['pspi']:.2f}  ({snapshot['pain_level']})\n"
        f"rPPG HR: {snapshot['hr_bpm']:.0f} bpm  (quality={snapshot['hr_quality']})\n"
        f"Behavioural tag: {snapshot['tag']}\n"
        f"Observations: {snapshot['observations']}\n"
        f"Recent micro-events: {snapshot['micro_events'][-3:]}\n\n"
        f"Give ONE sentence starting with STATE:"
    )


class LLMReasoner:
    def __init__(self) -> None:
        self.provider = settings.llm_provider.lower()
        self.model = settings.llm_model
        self.cooldown = float(settings.llm_cooldown_seconds)
        self._last_call = 0.0
        self._client = None

        if not settings.enable_llm_reasoning or self.provider == "none":
            log.info("LLM reasoning disabled.")
            self.provider = "none"
            return

        if self.provider == "groq":
            if not settings.groq_api_key:
                log.warning("GROQ_API_KEY missing — LLM disabled.")
                self.provider = "none"
                return
            try:
                from groq import Groq
                self._client = Groq(api_key=settings.groq_api_key)
                log.info(f"Groq reasoner ready ({self.model}).")
            except Exception as e:
                log.error(f"Groq init failed: {e}")
                self.provider = "none"
        elif self.provider == "ollama":
            log.info(f"Ollama reasoner configured ({self.model} @ {settings.ollama_host}).")
        else:
            log.warning(f"Unknown LLM provider: {self.provider}")
            self.provider = "none"

    def available(self) -> bool:
        return self.provider != "none"

    def reason(self, snapshot: Dict) -> str:
        if not self.available():
            return ""
        now = time.time()
        if now - self._last_call < self.cooldown:
            return ""
        self._last_call = now

        user = _build_user_prompt(snapshot)
        try:
            if self.provider == "groq":
                resp = self._client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user},
                    ],
                    max_tokens=80,
                    temperature=0.2,
                )
                text = resp.choices[0].message.content.strip()
            elif self.provider == "ollama":
                payload = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user},
                    ],
                    "stream": False,
                    "options": {"temperature": 0.2, "num_predict": 80},
                }
                r = httpx.post(
                    f"{settings.ollama_host}/api/chat",
                    json=payload,
                    timeout=20.0,
                )
                r.raise_for_status()
                text = r.json()["message"]["content"].strip()
            else:
                return ""
        except Exception as e:
            log.error(f"LLM error: {e}")
            return ""

        # Post-condition: must start with STATE:
        if not text.startswith("STATE:"):
            text = f"STATE: {text}"
        return text
