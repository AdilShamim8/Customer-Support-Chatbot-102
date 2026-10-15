# Troubleshooting

Symptom → cause → fix, ordered by how often each actually happens.
Last verified: 2026-10-15. Deeper procedure: the runbooks.

## "The service won't start"

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `ValidationError: app_env` | Bad `APP_ENV` value in `.env` | One of: development/staging/test/production |
| `ModuleNotFoundError` | Deps not installed in the active venv | `make install`; check `which python` |
| Chroma/ES connection refused | Backing stores not up | `make up` then wait for `(healthy)` |
| `IndexNotReadyError` at first request | Index empty (fresh volume) | `make ingest` |

## "Streaming works locally, dies behind nginx"

The classic. Buffering is on. Three things must all hold:
1. `proxy_buffering off;` in the location (or `X-Accel-Buffering: no`
   header from the app)
2. `proxy_read_timeout` ≥ 120s (default 60s kills long generations)
3. `proxy_http_version 1.1;` + cleared `Connection` header

See `deploy/nginx/nginx.conf` - the exact config, annotated.

## "Answers got subtly worse"

Work the diagnostic matrix (docs/evaluation/metrics.md):

| Pattern | Diagnosis |
|---------|-----------|
| Context relevance ↓ only | Retrieval: corpus stale, chunking regressed |
| Faithfulness ↓ only | Generation: prompt or model change |
| Both correct-looking but correctness ↓ | Corpus content is wrong |

Then: `make evaluate`, diff against the last report in
`data/eval/report.json`. If a deploy preceded it - rollback first,
diagnose after (runbook rule).

## "429s everywhere"

- Did traffic actually spike? (viral wave) → cache absorbs duplicates;
  edge limit sheds the rest. This is the system working.
- No traffic change? → Redis unreachable → rate limiter fallback
  behavior + per-pod multiplication (ADR-0006 residual). Check Redis.

## "Pods crash-loop after deploy"

```bash
kubectl -n chatbot logs <pod> --previous | tail -50
kubectl -n chatbot get pod <pod> -o jsonpath='{.status.lastState}'
```
- OOMKilled → memory limit vs reranker batch size (kill-switch off as
  immediate mitigation)
- Config error → env/secret mismatch (readiness would have caught it,
  liveness restarts instead - check startupProbe window)

## "p99 latency crept up over a week"

In order of historical likelihood:
1. Corpus grew → context assembly bigger → check token counts in logs
2. Cache hit rate decayed (embedding drift) → dashboard panel
3. Provider regression (latency by provider panel)
4. Redis eviction storm → D6 in failure-modes.md

## Still stuck?

- [Failure modes catalog](../architecture/failure-modes.md) - the full
  degradation model
- [Data flow](../architecture/data-flow.md) - where the milliseconds go
- Open an issue with request_id + timestamp - traces are tail-sampled
  but errors are always kept
