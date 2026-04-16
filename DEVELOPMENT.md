# Development Guide

## Overview

The Patient Care Monitor is a scientifically-grounded multimodal monitoring system for caregivers. It combines facial analysis, pain detection, heart rate estimation, voice analysis, and text sentiment to provide real-time patient comfort and distress assessment.

## Key Design Principles

### 1. No Naive Emotion Labels
Per Barrett et al. (2019, PMID: 31313636), facial configurations do NOT reliably map 1:1 to discrete emotions. This system reports:
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

## Module Architecture

### Face Analyzer (`modules/face_analyzer.py`)
- **Input**: BGR image frame
- **Output**: Action Unit estimates, landmarks, geometric metrics
- **Method**: MediaPipe FaceLandmarker Tasks API with blendshape-to-AU mapping
- **Key Classes**: `FaceAnalyzer`, `FaceAnalysisResult`, `AUEstimates`

### Pain Detector (`modules/pain_detector.py`)
- **Input**: AUEstimates from face analyzer
- **Output**: PSPI score, pain level, confidence
- **Method**: Prkachin & Solomon Pain Intensity (PSPI) scale
- **Formula**: PSPI = AU4 + max(AU6, AU7) + max(AU9, AU10) + AU43
- **Key Classes**: `PainDetector`, `PainAssessment`, `PainLevel`

### rPPG Estimator (`modules/rppg_estimator.py`)
- **Input**: Forehead ROI from face analyzer
- **Output**: Heart rate estimate, confidence, signal quality
- **Method**: Green-channel temporal filtering + FFT
- **Key Classes**: `RPPGEstimator`, `HeartRateResult`

### Voice Analyzer (`modules/voice_analyzer.py`)
- **Input**: Audio segment (numpy array)
- **Output**: Vocal state, arousal, valence, features
- **Method**: Pitch autocorrelation, energy, spectral analysis
- **Key Classes**: `VoiceAnalyzer`, `VoiceAnalysisResult`, `VoiceFeatures`, `VocalState`

### Text Sentiment (`modules/text_sentiment.py`)
- **Input**: Text string (caregiver notes, patient speech)
- **Output**: Valence, arousal, pain/distress flags
- **Method**: Domain-specific lexicon with negation handling
- **Key Classes**: `TextSentimentAnalyzer`, `SentimentResult`

### Fusion Engine (`modules/fusion_engine.py`)
- **Input**: Results from all analysis modules
- **Output**: Unified patient state with alert level
- **Method**: Confidence-weighted late fusion
- **Key Classes**: `FusionEngine`, `PatientState`, `PatientAlertLevel`

## Data Flow

```
Camera Feed → Face Analysis → Action Units
                      │
                      ├── Forehead ROI → rPPG → Heart Rate
                      │
                      └── AUs → Pain Detector → PSPI Score
                                            │
Audio Input → Voice Analysis ────────────────┤
                                            │
Text Input → Text Sentiment ─────────────────┤
                                            ▼
                                    Fusion Engine
                                            │
                                    Alert System
                                            │
                                    Dashboard / UI
```

## Configuration

All configuration is centralized in `config.py`:

- `FaceConfig`: MediaPipe face mesh parameters
- `PainConfig`: PSPI thresholds
- `VoiceConfig`: Audio analysis parameters
- `RPPGConfig`: Heart rate estimation parameters
- `AlertConfig`: Alert system settings
- `SystemConfig`: Top-level configuration

## Error Handling Pattern

All modules follow this error handling pattern:

```python
import logging

logger = logging.getLogger(__name__)

def some_function(self, input_data):
    try:
        # Process data
        result = process(input_data)
        return result
    except (SpecificException1, SpecificException2) as e:
        logger.error(f"Specific error: {e}")
        return default_result
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return safe_default
```

## Logging

Use the centralized logging configuration:

```python
from utils.logging_config import get_logger

logger = get_logger(__name__)
logger.debug("Detailed diagnostic information")
logger.info("General informational messages")
logger.warning("Warning messages for potential issues")
logger.error("Error messages for failures")
```

## Testing Strategy

### Unit Tests
- Test individual module functions in isolation
- Mock external dependencies (camera, MediaPipe)
- Test edge cases and error conditions

### Integration Tests
- Test module interactions
- Test data flow through the pipeline
- Test with synthetic data

### Test Files
- `tests/test_pain_detector.py`: Pain detection tests
- `tests/test_text_sentiment.py`: Text sentiment tests
- `tests/test_fusion_engine.py`: Fusion engine tests

## Performance Considerations

### Frame Skipping
The system processes every N frames (configurable via `process_every_n_frames`) to maintain real-time performance.

### Buffer Sizes
- rPPG: 300 frames (~10 seconds at 30fps)
- Pain detector: 15 frames for temporal smoothing
- Fusion engine: 30 states for trend analysis

### Memory Management
- Deques with maxlen for bounded buffers
- No raw video storage by default
- Session logs contain only numerical data

## Scientific Validations

When adding new features:

1. **Literature Review**: Find peer-reviewed research supporting the method
2. **Citation**: Add reference to module docstring
3. **Limitations**: Document known limitations and edge cases
4. **Disclaimer**: Add appropriate disclaimers if clinical use is possible

## Deployment

### Local Deployment
```bash
python monitor.py
```

### Streamlit Dashboard
```bash
streamlit run dashboard.py
```

### Hugging Face Spaces (Gradio)
- Upload to Hugging Face Spaces
- Use `app.py` as entry point
- Ensure GPU is available for MediaPipe

## Troubleshooting

### MediaPipe Model Not Found
```bash
python3 -c "import urllib.request; urllib.request.urlretrieve('https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task', 'models/face_landmarker.task')"
```

### Camera Not Opening
- Check camera index (try 0, 1, 2)
- Ensure camera is not in use by another application
- On Windows, may need to install `opencv-python` instead of `opencv-python-headless`

### Low rPPG Accuracy
- Ensure consistent lighting
- Minimize subject movement
- Check that face is properly detected
- Signal quality is affected by skin tone and lighting conditions

## Future Enhancements

Potential areas for improvement:

1. **Deep Learning Models**: Replace rule-based methods with trained models for better accuracy
2. **Additional Modalities**: Add physiological sensors (e.g., wearable devices)
3. **Personalization**: Calibrate thresholds per individual patient
4. **Long-term Trending**: Analyze patterns over days/weeks
5. **Mobile Support**: Port to mobile platforms
