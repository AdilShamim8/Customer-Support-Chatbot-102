# Runbook: Incident Response

> Owner: @AdilShamim8 · Last drill: 2026-10-15 · Target MTTR: < 30 min sev-1

## Severity Definitions

| Sev | Meaning | Response |
|-----|---------|----------|
| 1 | Chat answers failing or materially wrong at scale | Page immediately, all hands |
| 2 | Degraded quality/latency, one dependency down | Page on-call |
| 3 | Single-pod issues, cost anomalies, alerts without user impact | Next business day |

## Universal First Five Minutes (every incident)

1. **Acknowledge** the page (so others know a human exists).
2. **Snapshot state**: `kubectl -n chatbot get pods,deploy,hpa -o wide`
   and screenshot the Grafana overview panel (evidence evaporates).
3. **Declare severity** - over-communicate early; downgrade later.
4. **Mitigate before diagnosing** if a fast lever exists (kill-switches
   below). Root cause can wait; user pain cannot.
5. **Start a timeline** (timestamped one-liners) - the postmortem is
   written from this.

## Kill-Switch Ladder (fastest mitigations first)

Every switch is a ConfigMap/env flip - no deploy required:

```bash
# Disable reranking (reranker suspect): precision dip, not outage
kubectl -n chatbot set env deploy/chatbot-api ENABLE_RERANKING=false

# Disable semantic cache (cache corruption suspect)
kubectl -n chatbot set env deploy/chatbot-api SEMANTIC_CACHE_ENABLED=false

# Switch LLM provider (provider outage - the most likely sev-1)
kubectl -n chatbot set env deploy/chatbot-api LLM_PROVIDER=anthropic

# Shed load at the edge during a viral wave
kubectl -n chatbot annotate ingress chatbot-api \
  nginx.ingress.kubernetes.io/limit-rps=5 --overwrite
```

Rollout of env changes: `kubectl -n chatbot rollout status deploy/chatbot-api`
(~60s with maxUnavailable=0).

## By-Symptom Playbooks

### Error rate above 2% (alert: HighErrorRate / ErrorBudgetFastBurn)

1. `curl -s localhost:8000/live && curl -s localhost:8000/ready` per pod
   (via debug pod) - liveness vs readiness tells you app vs dependency.
2. Check the **error code distribution** in logs: `code="llm_provider_error"`
   vs `code="vector_store_error"` vs `code="rate_limit_exceeded"`.
   - LLM codes dominate → provider play below.
   - Vector codes → index runbook.
   - 429s at edge → capacity/viral play.
3. If codes are `internal_error` (unclassified): **rollback the last
   deploy** (see rollback runbook) - unclassified errors after a deploy
   are the deploy.

### LLM provider outage

1. Confirm: provider status page + `chatbot_llm_requests_total{status="error"}`.
2. Flip `LLM_PROVIDER` to the secondary (kill-switch above).
3. Verify answers return: smoke `POST /api/v1/chat` with golden question.
4. If **both** providers down: traffic keeps getting `fallback_message`
   (correct behavior); consider edge rate-limit shed to protect quota
   for the recovery window.

### Latency p95 > 3s (alert: HighLatencyP95)

1. Where is the time? Check span waterfall: embedding vs retrieval vs
   rerank vs LLM first-token.
   - Retrieval slow → vector store saturation (D-tier); add read
     replicas or flip rerank off to shed CPU.
   - First-token slow → provider throttling (soft 429s) → provider play.
   - Rerank slow → `ENABLE_RERANKING=false` immediately, then re-tune.
2. Redis latency > 5ms? → memory saturation; LRU is thrashing (D6).

### Crash-looping pods (alert: PodRestartsLooping)

1. `kubectl -n chatbot logs <pod> --previous | tail -100` - startup
   exceptions are usually config (missing secret, bad env) after a change.
2. If OOMKilled (`lastState.terminated.reason`) → raise memory limit or
   flip rerank off (the known CPU/MEM hot spot) and investigate after.
3. Rollback if a deploy preceded the loop.

## Communication Rules

- Sev-1: public status update every 30 min even with no news ("still
  working, next update at HH:MM") - silence reads as indifference.
- Post-incident: blameless postmortem within 48h using the timeline;
  every action item becomes an issue with an owner and a date.
- Add the incident's regression to the golden eval set (ADR-0007) - an
  incident that doesn't improve the system repeats itself.
