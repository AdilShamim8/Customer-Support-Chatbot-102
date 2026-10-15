# System Overview

> Status: Active · Owner: @AdilShamim8 · Last reviewed: 2026-10-15

## What This System Is

A customer-support answer service built on Retrieval-Augmented Generation (RAG).
Users ask questions in natural language; the system retrieves the most relevant
slices of a curated knowledge base, assembles a prompt engineered for accuracy
and tone, generates a grounded answer with citations, and remembers the
conversation for multi-turn follow-ups.

The architecture is intentionally boring where it can be (stateless API pods,
standard backing stores) and deliberately clever where it must be (hybrid
retrieval, reranking, prompt assembly, evaluation gates).

## The Four Stages of One Question

```
User ──> Edge (nginx/ingress) ──> API pod ──> RAG Pipeline ──> Answer
                                      │
                    ┌─────────────────┼──────────────────┐
                    ▼                 ▼                  ▼
               RETRIEVAL         GENERATION        EVALUATION
          (parse→chunk→index)  (prompt→LLM→cite)  (score→log→learn)
```

1. **Retrieval** - The question is normalized (typo fix, query expansion),
   searched across a *hybrid* index (keyword BM25 + dense vectors fused via
   Reciprocal Rank Fusion), and the top candidates are reranked by a
   cross-encoder. Hybrid matters: exact product names and error codes are
   lexical signals; paraphrases and intent are semantic signals. Either
   alone measurably degrades recall on support corpora.
2. **Generation** - The reranked context is assembled into a prompt that
   separates system instructions from untrusted retrieved text (prompt-
   injection containment), applies the active strategy (zero-shot, few-shot,
   chain-of-thought, or role+context), and calls the LLM with groundedness
   constraints and citation instructions.
3. **Memory** - Conversation turns live in Redis with a TTL; the last N turns
   are injected as context so follow-ups ("and how do I return *that*?")
   resolve without repeating the whole question.
4. **Evaluation** - Every answer is scored on context relevance (did we
   retrieve the right things?), faithfulness (does the answer follow from
   the context?), and answer correctness (does it match ground truth?).
   Scores feed the feedback loop that drives RAFT fine-tuning.

## Component Map

| Component | Technology | Scale Unit | Fails How? |
|-----------|-----------|------------|------------|
| API tier | FastAPI + gunicorn/uvicorn | Pod (HPA 6→1000) | Restarted by kubelet; traffic re-routed |
| Vector search | Chroma/FAISS (dev), managed vector DB (prod) | Shard | Degraded recall, flag-guarded |
| Keyword search | Elasticsearch/BM25 | Shard | Falls back to vector-only |
| Reranker | Cross-encoder / Cohere | In-process | Kill-switch disables, top-k passes through |
| LLM | OpenAI/Anthropic/local | Provider quota | Circuit breaker → fallback message |
| Cache/memory | Redis | Node | Degrades to stateless mode |
| Durable store | Postgres | Instance | HA failover; feedback queue buffers |
| Observability | Prometheus/Grafana/OTel | - | Never ranks above serving |

## Design Principles (in priority order)

1. **The answer must be grounded.** An "I don't know" that cites nothing
   beats a confident hallucination. Every generation prompt enforces it;
   evaluation measures it.
2. **Degrade, never die.** Every dependency has a defined degraded mode
   (see [failure-modes.md](failure-modes.md)). The service's job is to keep
   answering *something* useful while dependencies burn.
3. **Stateless serving.** Anything that holds user state lives outside the
   pod. This is what makes 6→1000 pod autoscaling a routing decision, not
   an architecture change.
4. **Measure before you tune.** No prompt or retrieval change ships without
   an evaluation delta (see [evaluation/metrics.md](../evaluation/metrics.md)).
5. **Boring where possible.** Postgres, Redis, standard Kubernetes - the
   innovation budget is spent on retrieval quality, not infrastructure
   novelty.

## Repository Layout

```
├── src/                  # Application code
│   ├── api/              #   FastAPI routes, middleware, auth
│   ├── parsing/          #   Document parsing (rule-based, AI-based)
│   ├── indexing/         #   Embeddings, keyword/vector/hybrid indexes
│   ├── retrieval/        #   Retriever, reranker, search strategies
│   ├── generation/       #   Prompt engine, LLM clients, RAFT
│   ├── pipeline/         #   RAG orchestration, conversation state
│   ├── evaluation/       #   Metrics, evaluator, benchmarks
│   ├── monitoring/       #   Metrics, tracing
│   └── core/             #   Exceptions, shared primitives
├── configs/              # Pydantic settings, logging
├── deploy/               # Kubernetes, Terraform, nginx
├── monitoring/           # Prometheus, Grafana, alerts, OTel
├── migrations/           # Alembic DB migrations
├── scripts/              # Ingest, evaluate, finetune, release
├── tests/                # unit / integration / e2e / load
├── data/                 # Knowledge base sources and eval sets
└── docs/                 # This documentation
```

## Further Reading

- [Scaling to 100M-200M users](scaling-100m-users.md)
- [Failure modes and degraded states](failure-modes.md)
- [Capacity planning model](capacity-planning.md)
- [ADRs](adr/) - why hybrid search, why SSE, why per-tier rate limits
- [Operations: SLOs](../operations/slo.md) · [Runbooks](../runbooks/)
