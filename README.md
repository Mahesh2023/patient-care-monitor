# Patient Care Monitor

**A scientifically-grounded multimodal monitoring system for caregivers**

> **Live Demo:** [https://fa5353ef4297ce.lhr.life](https://fa5353ef4297ce.lhr.life)

This system combines facial analysis, pain detection, heart rate estimation, voice analysis, and text sentiment to provide caregivers with real-time patient comfort and distress assessment.

## Architecture

```
Camera Feed ──→ Face Analysis (MediaPipe) ──→ Action Unit Estimation
                      │                              │
                      ├── Forehead ROI ──→ rPPG (Heart Rate)
                      │                              │
                      └── AU Estimates ──→ Pain Detection (PSPI)
                                                     │
Audio Input ──→ Voice Analysis ──────────────────────┤
                                                     │
Text Input ──→ Text Sentiment ───────────────────────┤
                                                     ▼
                                          Multimodal Fusion Engine
                                                     │
                                          ┌──────────┴──────────┐
                                          ▼                     ▼
                                   Alert System          Dashboard / UI
                                          │
                                   Session Logger
```

## Modules

| Module | File | Method | Scientific Basis |
|--------|------|--------|-----------------|
| Face Analysis | `modules/face_analyzer.py` | MediaPipe Face Mesh 468-point landmarks → geometric AU estimation | FACS (Ekman & Friesen, 1978) |
| Pain Detection | `modules/pain_detector.py` | PSPI = AU4 + max(AU6,AU7) + max(AU9,AU10) + AU43 | Prkachin & Solomon; Lucey et al. (2011) |
| Heart Rate (rPPG) | `modules/rppg_estimator.py` | Green-channel temporal filtering + FFT from forehead ROI | Poh, McDuff & Picard (2010) |
| Voice Analysis | `modules/voice_analyzer.py` | Pitch (autocorrelation), energy, spectral centroid | Schuller et al. (2018) |
| Text Sentiment | `modules/text_sentiment.py` | Domain-specific medical/care lexicon + negation handling | Russell (1980) dimensional model |
| Fusion Engine | `modules/fusion_engine.py` | Confidence-weighted late fusion with temporal smoothing | Poria et al. (2017) |
| Alert System | `alerts/alert_system.py` | Cooldown + consecutive-frame threshold | Clinical alert fatigue literature |
| Dashboard | `dashboard.py` | Streamlit real-time visualization | — |

## Key Design Decisions

### 1. No Naive Emotion Labels
Per **Barrett et al. (2019, PMID: 31313636)** — the landmark review in *Psychological Science in the Public Interest* — facial configurations do NOT reliably map 1:1 to discrete emotions. A furrowed brow can mean anger, concentration, confusion, or pain. This system reports:
- **Action Units** (what muscles are doing)
- **Dimensional states** (comfort, arousal, pain levels on continuous scales)
- **Behavioral observations** (what we see, not what we interpret)

### 2. Privacy-First
- All processing runs locally on-device
- No data is sent to any cloud service
- Raw video is never saved by default
- Session logs contain numerical data only, no images

### 3. Transparent and Explainable
- Rule-based methods (not black-box ML) for core analysis
- Every threshold has a scientific citation
- Confidence scores accompany all outputs
- Alert reasons are always stated explicitly

### 4. Supplement, Not Replace
This is a monitoring aid for caregivers. It does NOT:
- Diagnose medical conditions
- Replace professional clinical assessment
- Provide medical advice
- Claim to "read minds" or detect specific emotions reliably

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Demo mode (no camera needed)
python monitor.py --demo

# Real-time camera monitoring
python monitor.py

# Dashboard (requires streamlit)
streamlit run dashboard.py

# Process a video file
python monitor.py --video recording.mp4
```

## Output Dimensions

The system produces these continuous scores (not discrete emotion labels):

| Dimension | Range | Meaning |
|-----------|-------|---------|
| **Comfort Level** | 0-1 | 0 = very uncomfortable, 1 = very comfortable |
| **Arousal Level** | 0-1 | 0 = unresponsive/calm, 1 = very agitated |
| **Pain Level** | 0-1 | Based on PSPI (0-16 scale, normalized) |
| **Engagement** | 0-1 | 0 = not facing camera, 1 = eyes open, engaged |
| **Heart Rate** | bpm | Estimated via rPPG (not medical-grade) |

## Alert Levels

| Level | Meaning | Example Trigger |
|-------|---------|-----------------|
| **Normal** | No concerns | All indicators nominal |
| **Attention** | Worth noting | Heart rate slightly elevated |
| **Concern** | Should check | Moderate pain + vocal distress |
| **Urgent** | Immediate attention | Severe pain indicators sustained |

Alerts have:
- **Cooldown period** (30s default) to prevent alert fatigue
- **Consecutive frame threshold** (5 frames) to prevent false positives
- **Reason attribution** — always states why the alert fired

## Scientific References

1. **Barrett, L.F., et al.** (2019). Emotional Expressions Reconsidered: Challenges to Inferring Emotion From Human Facial Movements. *Psychological Science in the Public Interest*, 20(1), 1-68. PMID: 31313636

2. **Coles, N.A., et al.** (2019). A multi-lab registered replication of the facial feedback hypothesis. *Nature Human Behaviour*. PMID: 30973236

3. **Ekman, P., & Friesen, W.V.** (1978). *Facial Action Coding System: A Technique for the Measurement of Facial Movement*. Consulting Psychologists Press.

4. **Lucey, P., et al.** (2011). Painful data: The UNBC-McMaster shoulder pain expression archive database. *IEEE International Conference on Automatic Face & Gesture Recognition*.

5. **Poh, M.Z., McDuff, D.J., & Picard, R.W.** (2010). Non-contact, automated cardiac pulse measurements using video imaging and blind source separation. *Optics Express*, 18(10), 10762-10774.

6. **Poria, S., et al.** (2017). A review of affective computing: From unimodal analysis to multimodal fusion. *Information Fusion*, 37, 98-125.

7. **Prkachin, K.M.** (1992). The consistency of facial expressions of pain: a comparison across modalities. *Pain*, 51(3), 297-306.

8. **Russell, J.A.** (1980). A circumplex model of affect. *Journal of Personality and Social Psychology*, 39(6), 1161-1178.

9. **Schuller, B., et al.** (2018). Speech emotion recognition: Two decades in a nutshell, benchmarks, and ongoing trends. *Communications of the ACM*.

10. **Soukupova, T., & Cech, J.** (2016). Eye blink detection using facial landmarks. *21st Computer Vision Winter Workshop*.

## Limitations

- **AU estimation from landmarks** is less precise than EMG-based FACS coding or purpose-trained neural networks. Geometric approximations provide useful signals but are not certified FACS scores.
- **rPPG heart rate** is affected by lighting, movement, camera quality, and skin tone. It should not be used for clinical diagnosis.
- **Voice analysis** uses simple signal processing. Production systems should consider deep learning models trained on clinical datasets.
- **Pain expression varies** across individuals, cultures, and conditions. Some patients suppress pain displays (stoicism bias).
- **The system cannot detect internal states directly.** Per Barrett et al. (2019), all facial readings are behavioral observations, not windows into the mind.

## License

For research and educational purposes. Not FDA-approved for clinical use.
