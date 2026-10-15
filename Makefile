.PHONY: help install dev build up down logs test evaluate ingest

help:
	@echo "Customer Support Chatbot - Available commands:"
	@echo ""
	@echo "  make install     Install Python dependencies"
	@echo "  make dev         Run in development mode"
	@echo "  make build       Build Docker image"
	@echo "  make up          Start all services"
	@echo "  make down        Stop all services"
	@echo "  make logs        Tail application logs"
	@echo "  make test        Run test suite"
	@echo "  make ingest      Ingest sample documents"
	@echo "  make evaluate    Run evaluation suite"

install:
	pip install -r requirements.txt
	python -m nltk.downloader punkt stopwords

dev:
	APP_ENV=development python -m uvicorn src.api.main:app \
		--reload --host 0.0.0.0 --port 8000

build:
	docker build -t customer-support-chatbot:latest .

up:
	docker-compose up -d
	@echo "Services started. API available at http://localhost:8000"
	@echo "Docs available at http://localhost:8000/docs"

down:
	docker-compose down

logs:
	docker-compose logs -f chatbot

test:
	pytest tests/ -v --tb=short --asyncio-mode=auto

test-unit:
	pytest tests/unit/ -v --tb=short

test-integration:
	pytest tests/integration/ -v --tb=short --asyncio-mode=auto

ingest:
	python scripts/ingest_documents.py \
		--source-dir ./data/raw \
		--chunk-strategy hierarchical \
		--parse-strategy rule_based

evaluate:
	python scripts/evaluate_pipeline.py \
		--dataset ./data/eval/test_set.jsonl \
		--output ./data/eval/report.json

format:
	black src/ tests/ scripts/
	isort src/ tests/ scripts/

lint:
	flake8 src/ tests/ --max-line-length=100
	mypy src/ --ignore-missing-imports

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .mypy_cache