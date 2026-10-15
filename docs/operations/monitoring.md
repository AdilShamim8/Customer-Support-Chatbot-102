# Monitoring and Observability Guide

> Status: Active · Owner: @AdilShamim8 · Last reviewed: 2026-10-15

## The Three Questions Observability Must Answer

1. **Is the service healthy right now?** (metrics, dashboards, alerts)
2. **Why is this specific answer slow/wrong?** (traces + logs with IDs)
3. **Is quality drifting over weeks?** (eval metrics as time series)

Each needs a different instrument; no single one suffices.

## Instrumentation Map

| Signal | Tool | Where it lives |
|--------|------|----------------|
| Request metrics | prometheus-fastapi-instrumentator | `/metrics` per pod, scraped |
| Business metrics | `src/monitoring/metrics.py` (custom counters/histograms/gauges) | same `/metrics` |
| Structured logs | structlog (JSON) | stdout → cluster collector |
| Distributed traces | OpenTelemetry → OTel collector (tail-sampled) | Tempo/Jaeger |
| Eval scores | evaluation pipeline → push gateway or direct expose | `chatbot_eval_*` gauges |
| Dashboards | Grafana (`monitoring/grafana/`) | provisioned, in git |
| Alerts | Prometheus rules (`monitoring/alerts.yml`) | Alertmanager → paging |

## Golden Dashboard Panels (the 6 that matter in an incident)

1. **Request rate + error rate** (5xx ratio) - the availability pulse.
2. **Latency p50/p95/p99** - the speed pulse; first-token overlay for
   streaming health.
3. **Cache hit rate** - silent cost/latency regressions (D1) live here.
4. **LLM provider latency + error split by provider** - external deps.
5. **In-flight requests + pod count** - saturation vs HPA response.
6. **Fallback answer rate** - users effectively unserved while "up".

Anything not on this list is diagnostic depth, not incident surface -
keep the golden page clean enough to read at 3am.

## Logs: Structure and Rules

Every request log line carries: `request_id`, `conversation_id` (hashed),
`path`, `status`, `duration_ms`, and `trace_id` when tracing is on.

Rules enforced by config:
- **No prompts or answers at INFO** - full prompt text logs only at
  DEBUG in non-production (privacy + log-volume cost).
- **No secrets ever** - the settings loader masks key material; gitleaks
  guards the repo, the logger guards runtime.
- **Errors log the typed code** (`[llm_provider_error]`) so
  `grep code=llm_provider_error` works in any log store.

## Traces: Sampling Strategy

Tail-based sampling in the collector (`monitoring/otel-collector.yaml`):
- 100% of error traces, 100% of >3s slow traces, 10% baseline.
- Health/metrics paths filtered out pre-export.
- The trace for one chat request spans: API → embed → retrieve (keyword
  + vector in parallel) → rerank → prompt-assembly → LLM (with
  first-token event) → post-process. That waterfall IS the diagnostic
  playbook for latency incidents.

## Cardinality Discipline (the invisible outage)

High-cardinality labels (user_id, full prompt hashes) explode
Prometheus series counts and take monitoring down with the app. Rules:
- Label by `status`, `provider`, `strategy` - bounded sets only.
- Per-user/per-conversation facts belong in logs/traces, never metrics.
- The dashboard variables are the sanctioned drill-down dimensions.

## Runbooks That Use This Data

- Latency diagnosis: [incident-response.md](../runbooks/incident-response.md#latency-p95--3s)
- Drift detection: [failure-modes.md D2](../architecture/failure-modes.md)
- Alert definitions with runbook links: `monitoring/alerts.yml`
