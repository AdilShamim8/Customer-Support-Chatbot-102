# ADR-0003: Cross-Encoder Reranking as a Kill-Switchable Stage

- Status: Accepted
- Date: 2026-10-15
- Deciders: @AdilShamim8

## Context

First-stage retrieval optimizes recall (top-50 candidates cheaply); the
final prompt context budget fits ~5 chunks. The gap between them is
precision ordering - which 5 of the 50 actually answer *this* question.

Bi-encoder similarity (used for retrieval) scores the question and
candidate independently - cheap, but blind to token-level interaction.
Cross-encoders jointly encode (question, candidate) pairs: markedly
better ordering, markedly more compute (in-process, ~10-50ms/pair on
CPU, 50 pairs = 0.5-2.5s of CPU per request).

## Decision

Add a rerank stage between retrieval and generation:
- Candidates: top-50 from hybrid retrieval (RRF-fused).
- Reranker: cross-encoder locally (`sentence-transformers`) or Cohere
  API when configured; factory picks best available.
- Output: top-5 (TOP_K_RERANK) into the prompt context.
- **Kill-switch**: `ENABLE_RERANKING=false` bypasses the stage and
  passes retrieval order through - a config flip, not a deploy.

## Alternatives Considered

- **No reranking**: measurable precision loss on ambiguous questions;
  the golden-set eval showed faithfulness dropping with misordered
  context (models trust the first chunks disproportionately).
- **Rerank-all-candidates on GPU service**: best quality, but adds a
  GPU dependency to a CPU-serving tier - cost and ops complexity that
  a support workload does not justify.
- **LLM-as-reranker**: adds a full LLM round-trip to the hot path.

## Consequences

- + Precision at the context stage; eval gates on answer-correctness
  improved measurably vs. no-rerank baseline.
- + Graceful degradation built-in: reranker problems become slightly
  worse ordering, never an outage (failure-modes D3).
- − CPU-bound work in the API pod - deliberately allowed to drive HPA
  scale-out (it is the honest cost of quality); burst CPU limits are
  set so it can't starve the event loop into timeout.
