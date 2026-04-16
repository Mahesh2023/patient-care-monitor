# Contributing to Patient Care Monitor

Thank you for your interest in contributing to the Patient Care Monitor project!

## Development Setup

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd patient-care-monitor
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Download the MediaPipe face landmarker model**
   ```bash
   python3 -c "import urllib.request; urllib.request.urlretrieve('https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task', 'models/face_landmarker.task')"
   ```

## Running the System

### Demo Mode (No camera required)
```bash
python monitor.py --demo
```

### Webcam Mode
```bash
python monitor.py
```

### Video File Mode
```bash
python monitor.py --video path/to/video.mp4
```

### Streamlit Dashboard
```bash
streamlit run dashboard.py
```

### Gradio Dashboard
```bash
python app.py
```

## Running Tests

Run the test suite:
```bash
pytest
```

Run with verbose output:
```bash
pytest -v
```

Run specific test file:
```bash
pytest tests/test_pain_detector.py
```

Run with coverage:
```bash
pytest --cov=modules --cov=alerts --cov=utils
```

## Project Structure

```
patient-care-monitor/
├── modules/              # Core analysis modules
│   ├── face_analyzer.py      # Facial Action Unit estimation
│   ├── pain_detector.py      # PSPI-based pain detection
│   ├── rppg_estimator.py     # Heart rate from facial video
│   ├── voice_analyzer.py     # Voice feature extraction
│   ├── text_sentiment.py     # Text sentiment analysis
│   └── fusion_engine.py      # Multimodal fusion
├── alerts/               # Alert system
│   └── alert_system.py
├── utils/                # Utilities
│   ├── session_logger.py     # Session data logging
│   └── logging_config.py     # Centralized logging
├── tests/                # Unit tests
├── models/               # MediaPipe model files
├── monitor.py            # Main CLI entry point
├── dashboard.py          # Streamlit dashboard
├── app.py                # Gradio dashboard
├── config.py             # Configuration
└── requirements.txt      # Dependencies
```

## Code Style

- Follow PEP 8 style guidelines
- Use type hints where appropriate
- Add docstrings to all public functions and classes
- Use the existing logging infrastructure (`utils/logging_config.py`)
- Handle errors gracefully with try/except blocks

## Adding New Features

1. **New Analysis Module**: Create in `modules/` directory
   - Import logging: `logger = logging.getLogger(__name__)`
   - Add error handling with try/except blocks
   - Add corresponding unit tests in `tests/`

2. **New Configuration**: Add to `config.py`
   - Use dataclasses for configuration
   - Document scientific basis in docstrings

3. **New Alert Type**: Add to `alerts/alert_system.py`
   - Follow existing alert level structure
   - Add cooldown and threshold logic

## Scientific Basis

This project is grounded in peer-reviewed research. When adding features:

1. **Cite scientific literature** for the methodology
2. **Avoid emotion labels** per Barrett et al. (2019, PMID: 31313636)
3. **Report Action Units and physiological indicators**, not inferred emotions
4. **Include disclaimers** about limitations and appropriate use

See `README.md` for full scientific references.

## Logging

The project uses centralized logging via `utils/logging_config.py`:

```python
from utils.logging_config import get_logger

logger = get_logger(__name__)
logger.info("Information message")
logger.error("Error message")
```

## Testing

- Write tests for all new functionality
- Test both success and error cases
- Use pytest fixtures for common setup
- Aim for >70% code coverage

## Submitting Changes

1. Create a feature branch
2. Make your changes with clear commit messages
3. Run tests to ensure nothing is broken
4. Submit a pull request with description of changes

## Questions?

Feel free to open an issue for questions or discussion.
