FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (opencv, mediapipe, av/webrtc need these)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libgomp1 \
    libegl1 \
    libgles2 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code (includes models/face_landmarker.task)
COPY . .

# Create data directories
RUN mkdir -p data/session_logs

# Render.com sets PORT env var; default to 7860 for Gradio
ENV PORT=7860
EXPOSE ${PORT}

# Health check
HEALTHCHECK CMD curl --fail http://localhost:${PORT}/ || exit 1

# Run Gradio app
CMD python app.py
