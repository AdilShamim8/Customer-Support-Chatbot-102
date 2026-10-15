# Capacity Planning Model

> Status: Active · Owner: @AdilShamim8 · Last reviewed: 2026-10-15
>
> Numbers here feed `deploy/kubernetes/hpa.yaml`, Terraform instance sizing,
> and the budget alerts. Method: derive, don't guess - and re-derive after
> every load test, because the model drifts as prompts and models change.

## 1. Demand Model (per environment)

Baseline (100M MAU reference profile, see scaling doc for derivation):

| Quantity | Value | Formula |
|----------|-------|---------|
| Peak sustained RPS | 2,000 | DAU × turns × peak-hour-share ÷ 3600 |
| Burst RPS (viral) | 10,000 | 5× peak |
| Avg answer latency | 0.8s p50 / 3s p95 | measured (locust + prod telemetry) |
| Streaming connection hold | 2-15s | generation time |

## 2. Serving Tier

**Concurrency, not RPS, sizes this tier.** Little's Law:

```
in-flight requests  L = λ × W
                   = 2,000 req/s × 0.8 s
                   = 1,600 concurrent streams at peak
```

Per-pod capacity:
- 4 uvicorn workers (WEB_CONCURRENCY=4)
- Effective concurrent streams/pod: **40** (memory-bounded: 2Gi limit ÷
  ~50MB per active request context incl. rerank batches)
- **Pods at peak = 1,600 ÷ 40 = 40 pods**
- Headroom for zone loss (+34%) + burst (5×) → HPA max 1,000 covers ~25×
  peak - deliberate slack for quota-limited scale events

CPU: rerank cross-encoder dominates (~120ms/request on 2 vCPU) → 4 workers ×
0.5 RPS/worker ≈ 2 RPS/pod at full CPU... measured, not derived; the HPA
target (65% CPU / 40 RPS-per-pod custom metric) encodes the *measured*
value. Re-measure after any reranker model change.

## 3. Data Tier Sizing

### Redis (conversation memory + rate limits + semantic cache)
- Conversation state: 20 turns × ~1KB = 20KB/session; 15M sessions/day;
  TTL 1h → peak concurrent sessions ≈ peak RPS × 3600s... bounded by
  **active conversations**: 2,000 RPS × 1,800s avg session life ≈ 3.6M keys
  × 20KB ≈ **72GB hot set** → cache.r6g.2xlarge (128GB) leaves burst room.
- Rate-limit counters: ~10B per client per window - negligible.
- Semantic cache: 1 answer (~2KB) + 1 embedding (6KB) per cached question;
  1M cached questions ≈ 8GB - same instance, LRU evicts history first.

### Postgres (feedback + eval results)
- Feedback rows: 40M/day × ~500B = 20GB/day raw → partitioned monthly,
  90-day hot window ≈ **1.8TB** → 200GB start + storage autoscaling to 4×
  (Terraform), PITR window 30 days. Aggregates roll into summary tables
  nightly; raw rows are cold after 90 days.

### Vector index
- Corpus 100k docs → 50k words avg → 512-token chunks ≈ **400k chunks**;
  × 1536 dims × 4B = **2.4GB raw vectors** + HNSW graph (~1.5×) ≈ 4GB.
  Trivial for one node at this corpus size; the *QPS* is what forces
  replicas at scale (see scaling doc Tier 2b).

### Elasticsearch (keyword half)
- Same 400k chunks, ~1KB text each = 400GB... with 2-3× index overhead ≈
  **1.2TB** across a 3-node cluster. Fine at 100k docs; re-derive if the
  corpus reaches millions of docs.

## 4. LLM Throughput & Cost

- 40M generations/day × ~1,500 total tokens avg = **60B tokens/day**.
- Provider quotas: negotiate committed-use before sustained 2k RPS; the
  quota scheduler + cache (35-60% hit rate) is the difference between
  "fits in tier" and "hard wall".
- Cost per 1k answers is a first-class SLO (see operations/slo.md) - a
  prompt change that adds 20% tokens is a 20% cost regression and must be
  reviewed as such.

## 5. Verification Cadence

| When | Verify | How |
|------|--------|-----|
| Every release | latency + error rate unchanged | CI smoke + staging canary |
| Monthly | peak concurrency model vs reality | Grafana capacity dashboard |
| Before campaigns/product launches | burst survival (10k RPS) | locust 5m burst profile |
| Quarterly | full model re-derivation | this doc + load test numbers |

## 6. Provisioning Summary (production reference)

| Resource | Size | Why |
|----------|------|-----|
| API pods | 6 min / 40 typical / 1000 max | zone-loss floor + peak + burst slack |
| Node group | m6i.2xlarge × 6-300 | 8 vCPU/16GB fits 3-4 pods/node |
| Redis | cache.r6g.2xlarge × 2 (multi-AZ) | 72GB hot set + burst + failover |
| Postgres | db.r6g.2xlarge, 200GB→800GB autoscale | write rate + 90-day hot window |
| Vector | managed, 2-4 read replicas | QPS at peak |
| ES | 3 × 16GB nodes | index size + shard resilience |
