# Scaling CARE-MM to 1M+ users

## Workload model

A "user" here is a caregiver account; an active **stream** is one monitored patient with the tab open.
Concurrency is the sizing variable, not registered users. Assumption used below: 1M registered users,
≤10% concurrently streaming at peak → **100k concurrent streams**.

Per stream (v3 protocol): 2 WebSocket messages/s, ~1 KB each (5 samples × ~35 floats) ≈ 2 KB/s in,
~1.5 KB/s out; server CPU ≈ 1–3 ms per batch (AU mapping, PSPI, distress, alerts, rPPG FFT over 20 s);
DB writes: one small transaction per stream every 5 s + 1 metrics row/minute.

v2 comparison: JPEG upload (~50 KB/s) + MediaPipe on the server (~60–100 ms CPU per frame) — two to
three orders of magnitude more expensive per stream. Moving perception to the browser is what makes
1M-user scale economically possible.

## Capacity estimates (validate with `loadtest/ingest.js`)

| Component | Per-unit capacity (estimate) | For 100k concurrent streams |
|---|---|---|
| Web (1 vCPU, 2 workers) | ~300–600 streams at 60% CPU | ~200–330 instances (or ~60–80 × 4-vCPU) |
| Postgres writes | 100k streams / 5 s flush ≈ 20k small TX/s + 1.7k metric rows/s | Partitioned `session_metrics` + PgBouncer; or 2–4 hash-sharded primaries (Citus) |
| Redis | rate-limit INCR + pub/sub ≈ 50–100k ops/s | 1 primary handles this; cluster mode for headroom |
| LLM | 1 summary / stream / 30 s ≈ 3.3k req/s | Exceeds hosted free tiers — raise cooldown, sample, or self-host vLLM; the circuit breaker degrades gracefully |

Run the load test against a staging deploy and set instance counts from the measured streams/instance.

## Stage 1 — Render (current blueprint, free → paid)

1. `plan: standard` (or `pro`) web + `scaling: {minInstances: 2, maxInstances: N, targetCPUPercent: 60}`.
2. Postgres `basic-4gb`+ with read replica; Key Value `standard` with persistence off.
3. Keep `WEB_CONCURRENCY` = vCPUs; size `DB_POOL_SIZE` so instances × workers × pool < max_connections
   (add PgBouncer as a private service when this binds).
4. Move maintenance to a Render Cron Job (`python -c "import asyncio; from app.services.maintenance import run_once; asyncio.run(run_once())"`).

Render caps autoscaling at a bounded instance count per service, which realistically supports
tens of thousands of concurrent streams.

## Stage 2 — 100k+ concurrent streams (multi-region cloud)

Code changes are small because the web tier is already stateless:

- **Compute:** containers on Kubernetes/ECS with HPA on CPU + active-stream gauge
  (`care_mm_ws_streams`); multiple regions behind geo-DNS / a global LB with WebSocket support.
  Clients reconnect with a fresh ticket on any instance — no sticky sessions required.
- **Write path:** replace the synchronous 5-second DB flush with a durable log
  (Kafka / Redis Streams): ws → `alerts`/`metrics` topics → batch consumers → Postgres/TimescaleDB.
  Alert fan-out already goes through pub/sub and is unchanged.
- **Database:** monthly range partitioning on `session_metrics(bucket_start)` and `alerts(created_at)`
  (retention becomes `DROP PARTITION`), TimescaleDB or Citus sharded by `patient_id`, read replicas for
  history/export queries.
- **Redis:** cluster mode; rate-limit keys are naturally hash-distributed.
- **Edge:** CDN for `/static` (assets are immutable and cache-busted); WAF + bot protection in front of
  `/api/auth/*`.
- **Identity:** keep HS256 for a single trust domain, or switch to RS256/JWKS when splitting services.
- **LLM:** dedicated inference pool with a request queue, per-tenant quotas, response caching by
  snapshot signature.

## SLOs & alerting (suggested)

- `/ready` availability 99.9%; WS batch p95 < 50 ms server-side (`care_mm_ws_batch_seconds`).
- Alert delivery (stream → watcher) p95 < 2 s.
- Page on: 5xx rate > 1%, `care_mm_ws_rejects_total{reason="protocol"}` spikes, DB pool timeouts,
  LLM circuit open > 10 min.
