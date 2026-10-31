#!/bin/sh
# Container entrypoint: migrate (advisory-locked, safe with N instances), then serve.
set -eu

if [ -n "${PROMETHEUS_MULTIPROC_DIR:-}" ]; then
  rm -rf "$PROMETHEUS_MULTIPROC_DIR"
  mkdir -p "$PROMETHEUS_MULTIPROC_DIR"
fi

python -m alembic upgrade head

# --proxy-headers: trust Render's edge for client IP / scheme (rate limits, logs).
exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --workers "${WEB_CONCURRENCY:-2}" \
  --proxy-headers \
  --forwarded-allow-ips '*' \
  --ws-max-size 131072 \
  --ws-ping-interval 20 \
  --ws-ping-timeout 20 \
  --timeout-keep-alive 15 \
  --timeout-graceful-shutdown 25 \
  --no-server-header \
  --no-access-log
