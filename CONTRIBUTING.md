# Contributing to Customer Support Chatbot

Thank you for considering a contribution! This document explains the
development process, coding standards, and quality gates every change
passes. Last updated: 2026-10-15.

## Development Setup

```bash
git clone https://github.com/AdilShamim8/Customer-Support-Chatbot-102.git
cd Customer-Support-Chatbot-102
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install pytest pytest-asyncio httpx black isort ruff flake8 mypy pre-commit
pre-commit install
cp .env.example .env        # set OPENAI_API_KEY
docker-compose up -d redis postgres elasticsearch
make ingest                 # build the sample knowledge base
make dev                    # http://localhost:8000/docs
```

Full walkthrough: [docs/development/getting-started.md](docs/development/getting-started.md).

## The Quality Gates (what CI enforces on your PR)

| Gate | Command | What it protects |
|------|---------|------------------|
| Lint | `make lint` | ruff + flake8 (style, bugbear patterns) |
| Types | `make typecheck` | mypy |
| Unit tests | `make test-unit` | Contracts without I/O |
| Integration | `make test-integration` | Route + store behavior |
| Coverage | CI `--cov-fail-under=60` | Untested code doesn't land |
| Security | CI security workflow | pip-audit, bandit, gitleaks, Trivy |
| Eval gate | CI on retrieval/generation paths | Answer quality (ADR-0007) |

Pre-commit runs lint + secret-scanning locally before every commit -
install it once and most CI failures never happen.

## Coding Standards

- **Version**: read from `src/__version__.py`, never hardcode.
- **Errors**: raise typed exceptions from `src/core/exceptions.py` with
  a `code`, `http_status`, and `transient` flag. Bare `Exception` fails
  review.
- **Settings**: everything flows through `configs/settings.py` + env
  vars documented in `.env.example`. No scattered `os.getenv`.
- **Prompts**: only via the prompt engine. Inline f-string prompts in
  business code fail review (eval-gated, injection-guarded surfaces).
- **Logging**: structlog with event names and key-value context; no
  f-string log messages, no secrets, no prompt text at INFO.
- **Metrics**: bounded-set labels only (no user IDs, no query text) -
  cardinality discipline per the monitoring guide.
- **Formatting**: black (100 cols) + isort; enforced by pre-commit.
- **Commits**: conventional commits (`feat(scope): ...`), one logical
  change per commit. The history IS the changelog's raw material.

## Pull Request Expectations

1. Small, single-purpose PRs - the PR template asks for a production
   impact assessment (blast radius, rollback plan, migration needs).
2. Tests: new behavior ships with tests in the matching tier
   (unit/integration/e2e).
3. Retrieval/prompt/model changes: include an eval delta - run
   `make evaluate` before/after and paste the metric comparison.
4. Docs: user-visible changes update `CHANGELOG.md`; architectural
   decisions get an ADR (`docs/architecture/adr/`, next number).
5. Security-sensitive paths (`src/api/auth.py`, `deploy/`, workflows,
   `migrations/`) require CODEOWNERS review by design.

## Architectural Decisions

If your change alters how the system works (not just what it does) -
new dependency, changed data flow, swapped default - write an ADR first
and link it in the PR. Seven exist today; number yours sequentially.
Superseding an old decision requires a new ADR that references it.

## Reporting Issues

Use the issue templates (bug/feature). Security issues go through
[private advisories](SECURITY.md), never public issues.

## License

By contributing, you agree your contributions are licensed under the
[MIT License](LICENSE).
