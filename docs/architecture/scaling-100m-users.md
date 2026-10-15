# Scaling to 100M-200M Active Users

> Status: Active · Owner: @AdilShamim8 · Last reviewed: 2026-10-15
>
> This document is the scale design the whole repository is organized around.
> Every limit, autoscaler setting, and cache TTL traces back to the arithmetic
> here. When reality diverges from this model, update the model - do not
> silently retune the cluster.

## 1. Translate "Users" into Numbers Engineering Can Size

Marketing says "100M monthly active users." Infrastructure sees:

| Metric | Derivation | Value |
|--------|-----------|-------|
| MAU | given | 100,000,000 |
| Daily active (10% of MAU) | typical support chat ratio | 10,000,000 |
| Sessions per DAU | 90th pct: 3, median: 1 | ~15,000,000 sessions/day |
| Turns per session | median 2, p95 8 | ~40,000,000 requests/day |
| Peak-hour factor | support traffic is diurnal, 15-20% of daily in top hour | 6,000,000-8,000,000 req/hr peak |
| **Peak RPS sustained** | ÷3600 | **~2,000 RPS** |
| **Peak RPS burst (viral)** | 5x spike on incident waves | **~10,000 RPS** |
| Answers per day | each turn = 1 LLM call (cache off) | ~40M LLM calls/day |

At 200M MAU, double everything. The architecture below is linear in pods
until you hit the three non-linear choke points: **LLM cost/quota, embedding
throughput, and vector-search QPS** - each has its own mitigation below.

## 2. Load Profile (Why Standard Web Scaling Advice Half-Applies)

Chat traffic is *not* like a CRUD API:

- **Long-lived requests.** A streaming answer holds its connection 2-15s,
  not 50ms. Connection pools, keepalives, and worker counts must be sized
  on *concurrency*, not RPS.
- **Bursty by nature.** A shipping delay or outage announcement creates a
  *flash crowd* of near-identical questions within minutes - this is the
  exact shape the semantic cache exists for.
- **Diurnal with a long tail.** Peak is 5-8x of 4am traffic but never zero;
  the fleet floor must still serve the trough with headroom for one AZ loss.

## 3. The Scaling Ladder

### Tier 1: Horizontal pods (solves 95% of it)

Stateless pods behind the Service; HPA scales 6 → 1,000 on CPU + RPS
(`deploy/kubernetes/hpa.yaml`). Sizing:

- Sustained peak ~2,000 RPS, target 40 concurrent streams/pod
  (uvicorn worker_connections 1000, but memory limits effective concurrency)
- Concurrency = RPS × avg latency: 2,000 × 0.8s ≈ 1,600 in-flight → **~40-60
  pods at peak**; at 200M MAU double it.
- The 1,000-pod ceiling is about provider quota slack, not architecture.
  Zone-spread + PDB keep one-AZ-loss survivable at any fleet size.

### Tier 2: The three real bottlenecks

**a) LLM cost and quota (the wall you hit first).**
40M generations/day is a seven-figure monthly bill at flagship-model pricing
and will exceed any provider's default quota long before your pods sweat.

Mitigations, in the order they pay back:
1. **Semantic cache** (~35-60% hit rate on support traffic): near-duplicate
   questions ("where is my order" × 400k users) served from Redis without an
   LLM call. Cache key = embedding similarity ≥ 0.95. This is the single
   highest-leverage lever; it is flag-gated (`SEMANTIC_CACHE_ENABLED`).
2. **Model routing**: route easy FAQ-shaped questions to a small/fast model,
   escalate ambiguity to the flagship. The `LLMClientFactory` already
   abstracts providers; routing policy rides on retrieval confidence.
3. **Provider fan-out**: multiple keys/accounts/regions with a token-bucket
   quota scheduler in front (per-provider circuit breakers already in the
   config surface).
4. **RAFT fine-tuned small models** for the top-20 intent clusters: the
   repo's `scripts/finetune_adapter.py` exists precisely for this path.

**b) Vector search QPS.**
A single Chroma/FAISS node saturates around low-thousands QPS. At 2,000 RPS
× (1 query + rerank scoring) you need:
- Managed vector DB (Pinecone/Qdrant cluster mode) or sharded self-hosted
  with an ANN index (HNSW: recall ~0.95 at 10-50x QPS of exact search).
- Read replicas for retrieval (indexes are append-mostly; replica lag of
  seconds is invisible to users).
- The reranker is CPU-bound and lives *in-process*: at high fleet size it is
  the CPU that drives HPA scale-out - intentionally so, because it is
  kill-switchable (`ENABLE_RERANKING=false`) and top-k ordering degrades
  gracefully to retrieval order.

**c) Embedding throughput.**
Query-time embeddings must be ≤ 30ms p99 (batch them, keep the model warm).
Ingest-time embeddings are a batch pipeline problem, not a serving problem -
run ingestion on separate workers with its own quota.

### Tier 3: Multi-region (when 200M is global)

Single-region latency: EU users see +100-150ms. For global 200M:
- Active-active regions, each with full pod fleet + Redis + vector replicas.
- Postgres: primary in one region, cross-region replicas, planned failover.
- The knowledge-base index is *region-portable* (it is derived data):
  nightly snapshot + stream of chunk writes keeps regions converged.
- Route by geo + health; burst failover is manual-by-default (split-brain
  on conversation state is worse than a minute of extra latency).

## 4. What Breaks First at Each Scale (Anticipated)

| Scale | First failure | Symptom | Response |
|-------|--------------|---------|----------|
| ~1k RPS | LLM provider 429s | Latency climbs, then 502s | Quota scheduler + cache + model routing |
| ~3k RPS | Embedding API quota | Ingestion lags, query latency flat | Batch queries, dedicated ingestion keys |
| ~5k RPS | Vector DB QPS ceiling | p95 retrieval latency 5x | ANN mode / read replicas / shard |
| ~8k RPS | Redis connection count | New conns refused | Redis proxy or client pool tuning |
| Any | Single-zone cloud event | 1/3 fleet gone | Zone spread + PDB (already in manifests) |
| Any | Viral incident wave | 10x RPS in minutes | Edge rate limit + cache + HPA fast-path |

## 5. Cost Guardrails

- HPA ceiling + per-environment budget alerts (Terraform tags every resource
  for cost attribution).
- Cache hit-rate dashboard panel - a silent cache regression is a 2x LLM bill.
- Token telemetry per answer (`llm_usage` already tracked in pipeline stats)
  feeds a cost-per-1k-answers SLO the business can watch.

## 6. Load Testing the Claims

`tests/load/locustfile.py` encodes this model. Before any scale event:

```
make load-test TARGET_RPS=2000 DURATION=10m   # sustained peak
make load-test TARGET_RPS=10000 DURATION=5m   # viral burst survival
```

Gate: zero 5xx, p95 < 3s, cache hit-rate ≥ 30% on repeated-question mix.
