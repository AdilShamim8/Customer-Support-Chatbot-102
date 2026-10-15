# Evaluation Metrics Reference

> Status: Active · Owner: @AdilShamim8 · Last reviewed: 2026-10-15
>
> Implementation: `src/evaluation/metrics.py`, `evaluator.py`,
> `benchmarks.py`; runner: `scripts/evaluate_pipeline.py`;
> dataset: `data/eval/`.

## The Three Metrics (and why exactly three)

Each metric catches a failure the other two cannot see. Diagnosing with
one is guesswork; the *pattern across all three* is a diagnosis.

### 1. Context Relevance — did we retrieve the right chunks?

**Definition**: overlap/alignment between the question and the retrieved
context (deterministic lexical + embedding similarity hybrid; LLM-judge
variant for the weekly deep run).

**Catches**: chunking regressions, index staleness (D2), embedding-model
contamination, retrieval-config drift (top_k, threshold).

**Signal pattern**:
- Low relevance + normal faithfulness → retrieval problem; generation is
  honestly reporting "I don't know".
- Relevance dropping over weeks → corpus staleness or index drift.

### 2. Faithfulness — is the answer supported by the context?

**Definition**: fraction of answer claims entailed by the retrieved
context (claim decomposition → per-claim support check).

**Catches**: prompt regressions, hallucination drift, CoT
rationalization (playbook §Strategy 3), model swaps.

**Signal pattern**:
- High relevance + low faithfulness → the model is embellishing:
  prompt/model problem, retrieval is fine.
- Faithfulness is the *anti-hallucination* metric: it does not care if
  the answer is *correct*, only that it is *grounded*.

### 3. Answer Correctness — does it match ground truth?

**Definition**: semantic + factual comparison against the golden answer
(entity/number exactness + meaning similarity).

**Catches**: end-to-end regressions of any origin - the metric that
tracks what the user experiences.

**Signal pattern**:
- Low correctness + high faithfulness + high relevance → **the corpus
  itself is wrong or stale** - the answer faithfully reports wrong docs.
  This pattern is the corpus-refresh alarm.

## Diagnostic Matrix

| Context Rel. | Faithfulness | Correctness | Diagnosis |
|:---:|:---:|:---:|---|
| high | high | high | healthy |
| low | high | low | **retrieval**: fix chunking/index/corpus coverage |
| high | low | varies | **generation**: prompt or model regression |
| high | high | low | **corpus**: docs are wrong/stale - content fix |
| low | low | low | everything failing (or eval set broken - check first) |

## Cost, Latency, and Safety (secondary gates)

- **Token cost per answer** (prompt+completion): a prompt "improvement"
  that costs +20% tokens is a 20% cost regression - tracked as an SLO.
- **p95 latency**: eval runs measure the serving shape too.
- **Refusal rate**: too high = over-conservative prompt; too low =
  hallucination risk. Target band: 5-15% on the golden set (which
  deliberately includes 10% unanswerable questions).

## The Golden Set

- Versioned in `data/eval/` alongside code - dataset changes review like
  code changes.
- Composition: 60% FAQ-shape, 20% multi-hop, 10% adversarial/unanswerable,
  10% edge-case phrasing. Every production incident contributes a case.
- Runs: per-PR (changed paths only) for the gate; weekly full run +
  1% production sampling for drift detection (`chatbot_eval_*` gauges).

## RAFT Connection (where evaluation meets training)

RAFT training data construction consumes these metrics directly:
- High-faithfulness/low-correctness chunks → strong RAFT training pairs
  (the model should learn to answer from *this* document).
- Distractor chunks (retrieved-but-irrelevant) are mixed into RAFT
  contexts by design - training the model to ignore them at inference.
- See `scripts/finetune_adapter.py` and `src/generation/raft.py`.
