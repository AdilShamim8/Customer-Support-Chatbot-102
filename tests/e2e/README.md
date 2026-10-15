# E2E Tests

Full-stack tests through the real API surface - the last line before
production. Last reviewed: 2026-10-15.

## What "E2E" Means Here

The application runs with REAL infrastructure (docker-compose stack:
redis, postgres, elasticsearch, chroma) and REAL ingestion (the sample
knowledge base), with only the LLM provider mocked or key-provided.
Unit and integration tiers isolate; this tier integrates.

## The Two Flows Under Test

1. **The golden conversation**: ask → retrieve → answer with citations →
   follow-up referencing the first turn → verify memory worked.
2. **The failure ladder**: kill a dependency → verify the documented
   degraded mode (failure-modes.md) is what actually happens, not what
   we assumed happens.

## Running

```bash
make up             # full stack with real stores
make ingest         # real knowledge base
make test-e2e       # against localhost:8000
```

## Rules

- E2E failures are release blockers by definition - no "known flaky"
  list; flakiness gets fixed or the test is lying.
- Assertions check the CONTRACT (schema, status, timing), never the
  exact prose of answers (that's evaluation's job, not E2E's).
- Each test cleans its conversation state - E2E tests that leak state
  create the next test's mystery failure.
