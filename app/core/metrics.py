"""Prometheus metrics with bounded label cardinality.

Labels are route templates / enum values only — never session or user ids
(v2 labelled by session_id, which grows without bound at scale).
Multi-worker safe when PROMETHEUS_MULTIPROC_DIR is set (see scripts/start.sh).
"""
from __future__ import annotations

import os

from prometheus_client import (
    CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Gauge, Histogram, generate_latest,
)

_MULTIPROC = bool(os.environ.get("PROMETHEUS_MULTIPROC_DIR"))

HTTP_REQUESTS = Counter("care_mm_http_requests_total", "HTTP requests", ["method", "route", "status"])
HTTP_LATENCY = Histogram("care_mm_http_request_seconds", "HTTP latency", ["route"],
                         buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5))
WS_STREAMS = Gauge("care_mm_ws_streams", "Active ingest streams", ["kind"],
                   multiprocess_mode="livesum")
WS_BATCHES = Counter("care_mm_ws_batches_total", "Feature batches processed")
WS_SAMPLES = Counter("care_mm_ws_samples_total", "Feature samples processed")
WS_BATCH_LATENCY = Histogram("care_mm_ws_batch_seconds", "Batch processing latency",
                             buckets=(0.0005, 0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1))
WS_REJECTS = Counter("care_mm_ws_rejects_total", "Rejected WS messages", ["reason"])
ALERTS = Counter("care_mm_alerts_total", "Alerts fired", ["level", "key"])
LLM_CALLS = Counter("care_mm_llm_calls_total", "LLM summary calls", ["outcome"])


def render_metrics() -> tuple[bytes, str]:
    if _MULTIPROC:
        from prometheus_client import multiprocess
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        return generate_latest(registry), CONTENT_TYPE_LATEST
    return generate_latest(), CONTENT_TYPE_LATEST
