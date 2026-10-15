# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2026-10-15

### Added
- Production CI/CD pipeline (lint, type-check, security scans, tests, Docker build)
- CodeQL advanced security analysis workflow
- Dependabot dependency automation (pip, Docker, GitHub Actions)
- Kubernetes deployment stack: Deployment, HPA (autoscaling), PDB, Ingress,
  NetworkPolicy, ConfigMap, and external Redis/Postgres manifests
- Terraform infrastructure-as-code for the full serving stack
- Nginx reverse-proxy configuration with connection and rate limits
- Gunicorn production server configuration (uvicorn workers)
- Prometheus alerting rules (latency SLO burn, error rate, saturation)
- OpenTelemetry collector configuration for distributed tracing
- Documentation site (MkDocs Material) with full operations content
- Architecture Decision Records (ADRs 0001-0007)
- Production runbooks: incident response, deployment, rollback, index rebuild
- System design documentation: scaling to 100M-200M MAU, failure-mode
  analysis, capacity planning, and SLO definitions
- Threat model and security hardening guide
- Prompt engineering playbook (zero-shot, few-shot, CoT, role/context)
- Evaluation metrics reference (context relevance, faithfulness,
  answer correctness)
- Unit and integration test expansion: settings, auth, middleware, schemas,
  health, admin routes
- Shared pytest fixtures and test configuration (`tests/conftest.py`)
- Release automation and preflight scripts
- Extended sample knowledge base (policies, shipping, returns, account)

### Changed
- Version single-source-of-truth moved to `src/__version__.py`
- README restructured with production deployment guide
- All documentation timestamps refreshed to 2026-10-15
- `pyproject.toml` completed with ruff, mypy, coverage, and bandit config
- Dependency floors tightened with lockfile-style constraints

### Fixed
- Missing `.gitignore` (repository hygiene risk)
- Hardcoded version strings scattered across modules
- Stale 2024 example timestamps in API documentation

## [1.0.0] - 2026-06-04

### Added
- Initial release: RAG pipeline with hybrid retrieval (BM25 + vector + RRF)
- Multi-provider LLM client (OpenAI, Anthropic, local)
- Prompt engine with zero-shot, few-shot, chain-of-thought, and
  role/context strategies
- Reranking stage (cross-encoder and Cohere)
- Conversation memory (in-process and Redis)
- FastAPI service with auth, rate limiting, and Prometheus metrics
- Alembic migrations and Postgres schema
- Evaluation harness: context relevance, faithfulness, answer correctness
- RAFT fine-tuning and PEFT/LoRA adapter scripts
- Docker multi-stage build and compose stack
- Load testing with Locust; Grafana dashboard
