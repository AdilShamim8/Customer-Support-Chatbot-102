# Request Lifecycle Data Flow
> Companion to the system overview - this is ONE request, step by step,
> with the failure branch at each hop. Last reviewed: 2026-10-15.

## Happy Path (p50 ≈ 800ms)

```
t=0ms     Client → nginx (TLS, edge rate limit 20r/s/IP)
t=2ms     nginx → pod (least_conn, keepalive pool)
t=3ms     RequestLoggingMiddleware: bind request_id
t=4ms     RateLimitMiddleware: Redis zcard (sliding window, per key/IP)
t=6ms     Auth dependency: sha256(key) lookup → AuthenticatedUser
t=8ms     ConversationManager: load last N turns from Redis
t=12ms    Query preprocessing: normalize, strip control chars
t=15ms    ┌─ keyword search (BM25/ES)        ─┐ parallel
t=45ms    └─ vector search (ANN, top-50)     ─┘ (~30ms, embed+search)
t=50ms    RRF fusion: two ranked lists → one (k=60)
t=55ms    Rerank: cross-encoder scores 50 pairs (kill-switchable)
t≈1800ms* ...see below - rerank on CPU is the local hot spot
t=90ms    Context assembly: top-5 chunks, untrusted framing, token budget
t=95ms    Prompt assembly: system + history + context + question
t=100ms   LLM call (stream starts)
t≈700ms   First token → SSE frames stream out
t≈1500ms  Last token → citations resolve → response logged → metrics +
          eval gauges updated → conversation turn appended to Redis
```
*Rerank runs while the LLM connection is being established; effective
added latency ≈ 40ms p50, ~300ms p95 for the CPU-bound tail.

## Follow-Up Turns

The second "and how long does that take?" costs less and knows more:
history is loaded at t=8ms, and if the new turn references the previous
topic the standalone-question reformulation may skip re-embedding the
whole query. Conversation TTL is 1h; the 61st minute silently starts a
fresh session (known fragility, tracked).

## Cache Hit Path (p50 ≈ 60ms)

```
t=0-6ms    edge + middleware + auth (same)
t=8ms      Semantic cache: embed question, similarity ≥ 0.95 → HIT
t=60ms     Cached answer + sources returned; conversation still updated
```
A 40% hit rate at peak is the difference between one and two LLM
providers on the critical path (see capacity planning §4).

## Failure Branches (where each step hands off to degradation)

| Step | Failure | Branch |
|------|---------|--------|
| Rate limit | Redis down | Fail open, alert fires (F2/D6) |
| Keyword search | ES down | Vector-only list (recall dip) |
| Vector search | Index down | Readiness false → pod leaves Service |
| Rerank | CPU starvation / error | Retrieval order passes through |
| LLM | Provider 5xx | Retry×3 → circuit open → fallback_message |
| Post-answer | Eval write fails | Buffer to log; chat unaffected |

## What Gets Recorded (the observability contract)

Every request leaves: one log line (request_id, status, duration),
one trace (spans per stage, tail-sampled), 5+ metrics (rate, latency
histogram, cache hit/miss, fallback count, eval gauges). The incident
runbook's "where is the time?" question is answered from exactly this.
