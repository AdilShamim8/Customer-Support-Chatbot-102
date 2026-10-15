# Test Strategy

Last updated: 2026-10-15. CI wiring: `.github/workflows/ci.yml`.

## The Tiers

| Tier | Path | Contract | Runtime |
|------|------|----------|---------|
| Unit | `unit/` | Modules in isolation - no I/O, no network | < 5s |
| Integration | `integration/` | Routes + stores together (redis service in CI) | < 60s |
| E2E | `e2e/` | Full stack through the API surface | < 5 min |
| Load | `load/` | Sustained peak + viral burst survival | Manual |

## What Each New Module Owes

New code ships with tests in the matching tier - the PR template's
quality-gates section asks for it, and CI's coverage floor (60%) enforces
a hard minimum.

## The Contracts Worth Knowing

- **Probe endpoints** (`integration/test_health.py`): `/live` must never
  depend on backing stores; `/ready` must fail when the pipeline is gone.
  These are the Kubernetes restart/traffic contracts.
- **Auth** (`unit/test_auth.py`): keys hash at rest, roles gate by
  hierarchy, failures return 401 without leaking key material.
- **Rate limiter** (`unit/test_rate_limiter.py`): fail-open on Redis
  loss; health endpoints bypass limiting entirely.
- **Version** (`unit/test_version.py`): greps the API layer for
  hardcoded version strings - the single-source-of-truth guard.
- **Exceptions** (`unit/test_exceptions.py`): every error carries a
  stable code, HTTP status, and retryability flag.

## Running

```bash
make test-unit          # fast loop while developing
make test-integration   # needs redis: make up
make load-test TARGET_RPS=2000 DURATION=10m   # capacity model verification
```

## Fixtures & Heavy Dependencies

`conftest.py` builds the FastAPI app against a stubbed RAG pipeline, so
route logic is testable without LLM keys. Tests needing the full ML
stack (torch, chromadb) skip locally with a reason and run in CI where
`requirements.txt` is installed in full - capability detection, never
silent skips.
