# Getting Started (Development)

> Last verified: 2026-10-15 · Time to first running answer: ~10 minutes

## Prerequisites

- Python 3.11+
- Docker + Docker Compose (for the backing stores)
- An OpenAI **or** Anthropic API key (a $5 credit is plenty for dev)

## 1. Clone and configure

```bash
git clone https://github.com/AdilShamim8/Customer-Support-Chatbot-102.git
cd Customer-Support-Chatbot-102

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install pytest pytest-asyncio httpx  # dev/test extras

cp .env.example .env
# edit .env: set OPENAI_API_KEY=sk-...  (everything else has dev defaults)
```

## 2. Start the backing stores (docker)

```bash
docker-compose up -d redis postgres elasticsearch
# wait for health:
docker-compose ps   # all three (healthy)
```

## 3. Initialize the knowledge base

```bash
make ingest    # parses data/sample_docs, chunks, embeds, indexes
```

What this actually does (the pipeline you'll be working inside):
`data/raw` docs → parse (rule-based/AI) → chunk (hierarchical) →
embed (1536d) → write to Chroma + Elasticsearch.

## 4. Run the API

```bash
make dev       # uvicorn --reload on :8000
```

- Docs UI: http://localhost:8000/docs (dev only)
- Chat: `POST /api/v1/chat` (set `ENABLE_AUTH=false` locally or create
  an `ADMIN_API_KEY` in `.env`)
- Streaming: `POST /api/v1/chat/stream` (SSE)

Smoke test one question:

```bash
curl -s localhost:8000/api/v1/chat \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $ADMIN_API_KEY" \
  -d '{"message": "What is your return policy?", "conversation_id": "dev-1"}' | jq
```

## 5. Run the tests

```bash
make test-unit         # fast, no network
make test-integration  # needs redis from step 2
```

## 6. Evaluate your changes

```bash
make evaluate          # runs the golden set, prints the 3 metrics
```

Before opening a PR: `pre-commit run --all-files` (install once with
`pip install pre-commit && pre-commit install`).

## Project Conventions (the short list)

- **Version**: read from `src/__version__.py` - never hardcode.
- **Errors**: raise typed exceptions from `src/core/exceptions.py`.
- **Settings**: everything through `configs/settings.py` + `.env` - no
  scattered `os.getenv`.
- **Prompts**: only via the prompt engine - no inline f-string prompts
  in business code (eval-gated, injection-guarded).
- **Commits**: conventional commits (`feat(scope): ...`), one logical
  change per commit - the history is the changelog's source.

## Where to Go Next

- Understand the pipeline: [architecture overview](../architecture/system-overview.md)
- Change prompts safely: [prompting playbook](../prompting/playbook.md)
- Know how it fails: [failure modes](../architecture/failure-modes.md)
- First contribution: pick an issue labeled `good-first-issue`
