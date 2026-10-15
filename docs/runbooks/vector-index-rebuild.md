# Runbook: Vector Index Rebuild

> Owner: @AdilShamim8 · Last reviewed: 2026-10-15
>
# Triggers

- `VectorStoreDown` / `index_not_ready` errors fleet-wide (F4).
- Context-relevance eval score collapsed after a corpus change (D2).
- Index corruption suspected (chunk counts diverge from source docs).
- Planned: after major corpus refresh or embedding model change.

# Key Fact That Shapes Everything

**The index is derived data.** The knowledge base in `data/raw` (and the
canonical doc store) is the source of truth; both the vector index and
the Elasticsearch keyword index are *rebuildable projections*. This is
why we can rebuild aggressively: no data is at risk, only availability.

# Zero-Downtime Rebuild (blue/green index)

```bash
# 1. Ingest into the NEW index name (suffix with date)
python scripts/ingest_documents.py \
  --source-dir ./data/raw \
  --index-name support_docs_20261015 \
  --parse-strategy rule_based \
  --chunk-strategy hierarchical

# 2. Verify the new index before touching traffic
python scripts/build_index.py --verify --index-name support_docs_20261015
#    Check: chunk count vs expectation, sample-query sanity, no empty chunks

# 3. Flip the serving pointer (env change, rolling - no downtime)
kubectl -n chatbot set env deploy/chatbot-api CHROMA_COLLECTION=support_docs_20261015

# 4. Watch retrieval health for 10 minutes
#    (chatbot_index_health, context-relevance canary, error rate)

# 5. Only after confidence: drop the old index
#    (Keep it for one day if storage allows - rollback is then instant.)
```

# Emergency Rebuild (index is down, users are affected)

If the index is *gone* (not just stale), the fastest safe path is
degraded-serving first, rebuild second:

1. If only the **keyword** index is down: retrieval auto-falls-back to
   vector-only (F5) - no action needed beyond the ES rebuild.
2. If only the **vector** index is down: flip `VECTOR_STORE_TYPE` is
   *not* automatic; rerank-off + keyword-forward is the degraded mode.
3. If **both** down: readiness fails fleet-wide by design; communicate
   a sev-1, rebuild both from `data/raw` (step 1 above), and the pods
   self-recover as `/ready` passes.

# Embedding Model Change (special case)

A model change makes ALL old vectors incomparable - mixing old and new
embeddings silently destroys retrieval quality (queries embed in the new
space against old-space vectors: recall collapses to noise).

Rules:
1. New index name is **mandatory** (blue/green, above).
2. Re-embed EVERYTHING - partial re-embedding is the silent killer.
3. Semantic cache must be **flushed** (`SEMANTIC_CACHE_ENABLED=false` or
   `redis-cli FLUSHDB` on the cache DB - cached answers keyed by old-space
   embeddings are wrong the same way).
4. Post-flip: run the eval canary; recall dip = contamination somewhere.

# Verification Checklist (every rebuild)

- [ ] Chunk count ≈ docs × expected-chunks-per-doc (±5%)
- [ ] Golden questions: context-relevance within 2% of last baseline
- [ ] Zero empty-text chunks (`--verify` reports them)
- [ ] Old index still serving until the flip is confirmed good
- [ ] Postmortem note if the rebuild was unplanned: what drifted?
