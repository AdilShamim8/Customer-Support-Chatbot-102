# ADR-0002: Hybrid Retrieval (BM25 + Dense Vectors, RRF Fusion)

- Status: Accepted
- Date: 2026-10-15
- Deciders: @AdilShamim8
- Supersedes: none

## Context

The knowledge base mixes two kinds of content with opposite lexical
properties:

1. **Exact-token content**: order numbers, error codes ("ERR_4402"),
   SKU names, policy numbers. Semantic embeddings blur these - two
   different error codes can embed near-identically.
2. **Paraphrase content**: "my parcel is late" vs "shipping delay" vs
   "where's my stuff". Pure keyword search misses all but the literal
   overlap; this is where dense retrieval shines.

Single-modality retrieval measurably fails one side or the other on a
support corpus.

## Decision

Retrieve with **both** a keyword index (BM25/Elasticsearch) and a dense
vector index (text-embedding-3-small, 1536d), then fuse the two ranked
lists with **Reciprocal Rank Fusion** before reranking:

```
RRF_score(d) = Σ over rankers r: 1 / (k + rank_r(d)),  k = 60
```

## Alternatives Considered

- **Dense-only + query expansion**: recovered some lexical cases, but
  expansion latency (~1 extra LLM/embedding call) hurt the 800ms p50
  budget and still missed exact codes.
- **Weighted score fusion**: requires comparable score scales across
  rankers; BM25 and cosine similarity are not commensurable without
  per-corpus calibration. RRF needs only ranks - robust to score-scale
  drift.
- **Linear blend with tuned weights**: brittle; every corpus refresh
  re-tunes. RRF's k=60 is famously insensitive.

## Consequences

- + Recall on both content types; no score calibration.
- + Either index can fail independently (see failure-modes F5) - the
  other still answers, with a quality dip rather than an outage.
- − Two indexes to build, keep consistent, and operate - ingestion
  writes both; index-rebuild runbook covers both.
- − p50 latency carries both lookups in parallel (they run concurrently,
  so wall-time ≈ max, not sum).
