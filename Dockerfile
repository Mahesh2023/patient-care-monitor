# CARE-MM v3 — multi-stage, non-root, CPU-only. No mediapipe/opencv on the
# server: face perception runs in the browser (self-hosted WASM assets).

# ---------- builder: deps + hash-verified frontend assets ----------
FROM python:3.12-slim AS builder
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
WORKDIR /build
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY scripts/fetch_assets.py scripts/fetch_assets.py
RUN python scripts/fetch_assets.py

# ---------- runtime ----------
FROM python:3.12-slim
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin app
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY alembic.ini ./
COPY alembic ./alembic
COPY src ./src
COPY app ./app
COPY scripts/start.sh ./scripts/start.sh
COPY --from=builder /build/app/static/vendor ./app/static/vendor

ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    ENVIRONMENT=production \
    LOG_JSON=true \
    PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus \
    PORT=8000

USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/health', timeout=4)" || exit 1

CMD ["sh", "scripts/start.sh"]
