# Customer Support Chatbot - Developer Command Surface
# Every common workflow should be one `make <target>` away.
# Production targets follow the runbooks in docs/runbooks/.

.PHONY: help install dev prod build up up-prod down logs \
	test test-unit test-integration test-e2e load-test verify \
	lint typecheck format precommit \
	ingest evaluate eval-gate smoke preflight release docs \
	clean docker-scan

help:
	@echo "Customer Support Chatbot - Commands:"
	@echo ""
	@echo "  Setup & Run"
	@echo "    make install        Install dependencies"
	@echo "    make dev            Run API in dev mode (uvicorn --reload)"
	@echo "    make prod           Run API with gunicorn (production profile)"
	@echo "    make up             Start dev backing stores (docker-compose)"
	@echo "    make up-prod        Start production-shaped stack"
	@echo "    make down           Stop all services"
	@echo "    make logs           Tail application logs"
	@echo ""
	@echo "  Quality"
	@echo "    make lint           ruff + flake8"
	@echo "    make typecheck      mypy"
	@echo "    make format         black + isort"
	@echo "    make precommit      install + run all pre-commit hooks"
	@echo ""
	@echo "  Tests"
	@echo "    make test           Full suite"
	@echo "    make test-unit      Fast, isolated"
	@echo "    make test-integration  Requires redis (make up)"
	@echo "    make load-test      Locust (TARGET_RPS=, DURATION=)"
	@echo "    make verify         Coherence gate before every PR"
	@echo ""
	@echo "  RAG Operations"
	@echo "    make ingest         Ingest knowledge base"
	@echo "    make evaluate       Full evaluation suite"
	@echo "    make eval-gate      CI gate: golden set vs baseline"
	@echo ""
	@echo "  Release"
	@echo "    make smoke          Post-deploy smoke (local)"
	@echo "    make preflight      Post-deploy smoke (staging/prod URL)"
	@echo "    make release        Version bump + tag (patch|minor|major)"
	@echo "    make docs           Serve documentation site locally"

# ── Setup & Run ──────────────────────────────────────────────────────────────

install:
	pip install -r requirements.txt
	pip install pytest pytest-asyncio httpx black isort ruff flake8 mypy
	python -m nltk.downloader punkt stopwords || true

dev:
	APP_ENV=development python -m uvicorn src.api.main:app \
		--reload --host 0.0.0.0 --port 8000

prod:
	APP_ENV=production python -m gunicorn src.api.main:app \
		--config gunicorn.conf.py

build:
	docker build -t customer-support-chatbot:latest .

up:
	docker-compose up -d
	@echo "Services started. API at http://localhost:8000 (docs at /docs)"

up-prod:
	docker compose -f docker-compose.prod.yml up -d
	@echo "Production-shaped stack up. Grafana at http://localhost:3001"

down:
	docker-compose down 2>/dev/null || true
	docker compose -f docker-compose.prod.yml down 2>/dev/null || true

logs:
	docker-compose logs -f chatbot

# ── Quality ─────────────────────────────────────────────────────────────────

lint:
	ruff check src/ configs/ scripts/ tests/
	flake8 src/ configs/ scripts/ tests/ --max-line-length=100 --extend-ignore=E203

typecheck:
	mypy src/ configs/ --ignore-missing-imports

format:
	black --line-length=100 src/ configs/ scripts/ tests/
	isort --profile=black --line-length=100 src/ configs/ scripts/ tests/

precommit:
	pip install pre-commit
	pre-commit install
	pre-commit run --all-files

# ── Tests ───────────────────────────────────────────────────────────────────

test:
	pytest tests/ -v --tb=short

# Whole-repo coherence gate: the local mirror of CI. One command that
# must be green before every PR: the hermetic unit suite, which already
# includes the golden-set, env-contract, manifest-integrity, metrics and
# import-isolation contracts. Integration/e2e stay separate targets -
# they need backing stores (make up) or a deployed environment.
verify:
	pytest tests/unit/ -q
	@echo "verify: OK - unit suite and repo integrity contracts are green"


test-unit:
	pytest tests/unit/ -v --tb=short -m "unit" --cov=src --cov=configs --cov-report=term-missing

test-integration:
	pytest tests/integration/ -v --tb=short

test-e2e:
	pytest tests/e2e/ -v --tb=short

load-test:
	@TARGET_RPS=$${TARGET_RPS:-200} DURATION=$${DURATION:-5m} \
	python -m locust -f tests/load/locustfile.py \
		--headless -u $$(($${TARGET_RPS:-200} * 2)) -r 20 \
		--run-time $${DURATION:-5m} \
		$${TARGET_HOST:+--host $$TARGET_HOST}

# ── RAG Operations ─────────────────────────────────────────────────────────

ingest:
	python scripts/ingest_documents.py \
		--source-dir ./data/sample_docs \
		--chunk-strategy hierarchical \
		--parse-strategy rule_based

evaluate:
	python scripts/evaluate_pipeline.py \
		--dataset ./data/eval/golden_faq.jsonl \
		--dataset ./data/eval/golden_multihop.jsonl \
		--dataset ./data/eval/golden_adversarial.jsonl \
		--output ./data/eval/report.json

eval-gate:
	python scripts/evaluate_pipeline.py \
		--dataset ./data/eval/golden_faq.jsonl \
		--output ./data/eval/gate_report.json --gate

# ── Release ─────────────────────────────────────────────────────────────────

smoke:
	./scripts/preflight.sh http://localhost:8000

preflight:
	@echo "Usage: make preflight URL=https://staging.example.com KEY=..."
	./scripts/preflight.sh $${URL:-http://localhost:8000} $${KEY:-}

release:
	./scripts/release.sh $${BUMP:-patch}

docs:
	pip install -q mkdocs-material
	mkdocs serve

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
