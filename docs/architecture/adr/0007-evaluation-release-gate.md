# ADR-0007: Evaluation as a Release Gate

- Status: Accepted
- Date: 2026-10-15
- Deciders: @AdilShamim8

## Context

RAG systems fail *qualitatively*: retrieval changes, prompt tweaks, and
model upgrades shift answer quality in ways unit tests cannot see.
"Tests pass, answers got worse" is the canonical RAG production incident -
and it is invisible until users complain.

The three metrics that matter (each catching a different failure):

1. **Context relevance** - did retrieval fetch the right chunks?
   (Catches indexing bugs, chunking regressions, corpus staleness.)
2. **Faithfulness** - is the answer supported by the retrieved context?
   (Catches prompt regressions and hallucination drift.)
3. **Answer correctness** - does it match ground truth end-to-end?
   (Catches everything else, noisily - hence the trio.)

## Decision

Make evaluation a **release gate**, not a dashboard:

- Golden question set (versioned in `data/eval/`) runs on every PR that
  touches `src/retrieval/`, `src/generation/`, or prompt templates.
- CI compares the three metrics against the `main` baseline; a drop
  beyond threshold fails the build (same status as a failing unit test).
- Human review sees the eval diff in the PR template's Quality Gates
  section - "what did this do to answer quality?" is a mandatory answer.
- Production scores stream to Prometheus (`chatbot_eval_*` metrics);
  drift triggers the D2 alert path in failure-modes.md.

RAFT fine-tuning consumes the same metrics: chunks where faithfulness
is high but correctness low are exactly the training signal RAFT wants
("answer from the right document, distractors present").

## Alternatives Considered

- **Manual spot-checks before release**: unscalable, uneven, and the
  checker's own expectations drift.
- **Production A/B only**: real users absorb the regression before it
  is measured - the exact failure mode this ADR exists to prevent.
- **LLM-as-judge only, no deterministic metrics**: judge drift and
  prompt sensitivity make the gate itself flaky; deterministic
  overlap-based context-relevance stays in the suite as a stabilizer.

## Consequences

- + Quality regressions block merges by construction.
- + The golden set becomes a strategic asset that compounds - every
  production incident adds a regression-test question.
- − Gate maintenance: thresholds need periodic recalibration as the
  corpus grows (tracked as a standing ops task).
- − Eval runtime adds ~minutes to CI on retrieval-affecting paths only
  (path-filtered workflow), not every PR.
