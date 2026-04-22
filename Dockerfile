# CARE-MM v2.0 container — single-stage, CPU-only, Render-ready.
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 libgomp1 curl \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY app ./app

# Pre-download MediaPipe model at build time so cold-start does NOT
# depend on runtime outbound network access. Saves to /app/models/.
RUN mkdir -p /app/models && \
    curl -fsSL -o /app/models/face_landmarker.task \
      https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task && \
    ls -la /app/models/face_landmarker.task

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    MODEL_DIR=/app/models \
    PORT=8000

EXPOSE 8000

# Render injects $PORT; use shell form so it is expanded at runtime.
CMD uvicorn app.server:app --host 0.0.0.0 --port ${PORT:-8000}
