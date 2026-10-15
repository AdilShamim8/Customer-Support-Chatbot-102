<div align="center">

# Project 2 - Build a Customer Support Chatbot using RAGs and Prompt Engineering
### Production-Grade RAG System with Prompt Engineering & PEFT Fine-Tuning


[![Python 3.11+](https://img.shields.io/badge/python-3.11+-3776AB.svg?style=flat&logo=python&logoColor=white)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg?style=flat&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4o-412991.svg?style=flat&logo=openai&logoColor=white)](https://openai.com/)
[![Docker](https://img.shields.io/badge/Docker-ready-2496ED.svg?style=flat&logo=docker&logoColor=white)](https://www.docker.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-F7DF1E.svg?style=flat)](LICENSE)
[![Code Style: Black](https://img.shields.io/badge/code%20style-black-000000.svg?style=flat)](https://github.com/psf/black)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg?style=flat)](CONTRIBUTING.md)

<!-- <p align="center">
  <img src="docs/assets/architecture.png" alt="Architecture Diagram" width="800"/>
</p> -->

**A fully production-ready AI customer support system built on**
**Retrieval-Augmented Generation (RAG), advanced prompt engineering,**
**hybrid search, reranking, and parameter-efficient fine-tuning.**
> ### To better understand this project, first visit this link for a visualization of the project and what I built: [Link](https://ragchatbot1.space-z.ai/)
> ### Then, if you want to learn each topic in a tutorial format, read this file thoroughly: [Link](https://github.com/AdilShamim8/Customer-Support-Chatbot-102/blob/main/Tutorial-102.md)

[Quick Start](#-quick-start) •
[Architecture](#-architecture) •
[Features](#-features) •
[Documentation](#-documentation) •
[API Reference](#-api-reference) •
[Evaluation](#-evaluation) •
[Contributing](#-contributing)

</div>

---

## 📋 Table of Contents

- [Overview](#-overview)
- [Features](#-features)
- [Architecture](#-architecture)
- [Project Structure](#-project-structure)
- [Prerequisites](#-prerequisites)
- [Quick Start](#-quick-start)
- [Configuration](#-configuration)
- [Document Ingestion](#-document-ingestion)
- [Prompt Engineering](#-prompt-engineering)
- [RAG Pipeline](#-rag-pipeline)
- [Fine-Tuning with PEFT/LoRA](#-fine-tuning-with-peftlora)
- [API Reference](#-api-reference)
- [Evaluation](#-evaluation)
- [Monitoring](#-monitoring)
- [Deployment](#-deployment)
- [Testing](#-testing)
- [Performance](#-performance)
- [Troubleshooting](#-troubleshooting)
- [Contributing](#-contributing)
- [License](#-license)

---

## 🌟 Overview

This system is a **production-grade customer support chatbot** that combines the
power of **Retrieval-Augmented Generation (RAG)** with **advanced prompt 
engineering** and **parameter-efficient fine-tuning (PEFT)**. It is designed 
to answer customer questions accurately by grounding responses in your own 
documentation — eliminating hallucinations and ensuring policy-compliant answers.

### Why This Exists

Traditional chatbots fail in three ways:
1. **They hallucinate** — generating confident but incorrect answers
2. **They go stale** — knowledge cutoffs mean outdated responses
3. **They are generic** — no awareness of your company's specific policies

This system solves all three:

| Problem | Solution |
|---|---|
| Hallucination | RAG grounds every answer in retrieved documents |
| Staleness | Documents are re-indexed on upload — no retraining |
| Generic responses | Role-specific prompting + user context injection |
| Poor retrieval | Hybrid search (BM25 + vectors) + cross-encoder reranking |
| Slow adaptation | PEFT/LoRA fine-tuning on RAFT-generated datasets |

### Key Design Decisions

```
┌─────────────────────────────────────────────────────────────┐
│  Why Hybrid Search?                                         │
│  Vector search excels at semantic similarity.               │
│  BM25 excels at exact keyword matching.                     │
│  Combined via RRF → best of both worlds.                    │
├─────────────────────────────────────────────────────────────┤
│  Why Reranking?                                             │
│  Bi-encoder retrieval is fast but imprecise.                │
│  Cross-encoder reranking is slow but highly accurate.       │
│  Retrieve 10 → rerank to top 5 = speed + precision.        │
├─────────────────────────────────────────────────────────────┤
│  Why RAFT over standard fine-tuning?                        │
│  RAFT trains the model to cite specific documents           │
│  and ignore distractors — purpose-built for RAG.            │
├─────────────────────────────────────────────────────────────┤
│  Why Hierarchical Chunking?                                 │
│  Preserves document structure (section → paragraph).        │
│  Prepends section context to every chunk.                   │
│  Dramatically improves retrieval recall.                    │
└─────────────────────────────────────────────────────────────┘
```

---

## ✨ Features

### 🔍 Retrieval & Indexing
- **6 chunking strategies**: Fixed-size, Sentence, Paragraph, Hierarchical,
  Semantic (embedding-based), Sliding Window
- **3 vector stores**: ChromaDB (local), FAISS (high-performance), 
  Pinecone (cloud-scale)
- **2 keyword engines**: BM25 (in-memory) and Elasticsearch (production)
- **Hybrid search** with Reciprocal Rank Fusion (RRF)
- **3 rerankers**: Cohere API, CrossEncoder (local), FlashRank (ultra-fast)
- **Document parsers** for PDF, DOCX, HTML, Markdown, TXT
  (both rule-based and AI-based via unstructured.io)

### 🧠 Generation & Prompting
- **Multi-provider LLM support**: OpenAI GPT-4o, Anthropic Claude 3
- **5 prompt strategies**: Zero-shot, Few-shot, Chain-of-thought,
  Role-specific, RAG-standard
- **User context injection**: Personalized responses by tier, history, language
- **Standalone question reformulation** for conversational follow-ups
- **Hallucination detection** via LLM-as-judge
- **Token budget management** with automatic context truncation
- **Streaming support** (SSE) with non-blocking async generators
- **Citation generation** with source attribution

### 🎯 Fine-Tuning
- **LoRA** (Low-Rank Adaptation) for parameter-efficient fine-tuning
- **QLoRA** (4-bit quantized LoRA) for single-GPU training of 7B+ models
- **RAFT data generation**: Automatic Q&A dataset creation with
  oracle/distractor mixing
- **Adapter merging** for zero-overhead production inference

### 📊 Evaluation
- **Context Relevance**: Are retrieved chunks relevant to the query?
- **Faithfulness**: Is the answer grounded in context (hallucination check)?
- **Answer Relevance**: Does the answer address the question?
- **Answer Correctness**: Factual accuracy vs. ground truth
- **ROUGE-L**: Lexical similarity scoring
- **Context Recall**: Token-overlap based recall estimation
- **RAGAS framework integration**
- **Automated evaluation CLI and API endpoint**

### 🚀 Production Infrastructure
- **FastAPI** with async endpoints, SSE streaming, and OpenAPI docs
- **Redis** for conversation state persistence (with in-memory fallback)
- **PostgreSQL** for conversation history, feedback, and document registry
- **Docker Compose** with 7 services (app, Redis, ChromaDB, 
  Elasticsearch, PostgreSQL, Prometheus, Grafana)
- **Prometheus metrics** + **Grafana dashboards**
- **Kubernetes-ready** liveness and readiness probes
- **GitHub Actions CI/CD** with lint, test, and Docker build stages
- **Structured logging** (JSON in production, colored console in dev)
- **Rate limiting** and **CORS** middleware
- **Alembic database migrations**

---

## 🏗 Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        CLIENT LAYER                                 │
│              Web App / Mobile / API Consumer                        │
└─────────────────────────┬───────────────────────────────────────────┘
                          │ HTTPS
                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      FastAPI APPLICATION                            │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────────────┐ │
│  │ Rate Limit  │  │   Request    │  │      CORS Middleware        │ │
│  │ Middleware  │  │   Logging    │  │                            │ │
│  └─────────────┘  └──────────────┘  └────────────────────────────┘ │
│                                                                     │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────────────┐ │
│  │  /chat      │  │  /admin      │  │  /health /ready /live      │ │
│  │  /feedback  │  │  /documents  │  │  /metrics                  │ │
│  │  /stream    │  │  /evaluate   │  │                            │ │
│  └──────┬──────┘  └──────┬───────┘  └────────────────────────────┘ │
└─────────┼────────────────┼─────────────────────────────────────────┘
          │                │
          ▼                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       RAG PIPELINE                                  │
│                                                                     │
│  User Query                                                         │
│      │                                                              │
│      ▼                                                              │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  1. CONVERSATION MANAGER                                     │   │
│  │     Load history → Redis / PostgreSQL                        │   │
│  └──────────────────────┬───────────────────────────────────────┘   │
│                         │                                           │
│  ┌──────────────────────▼───────────────────────────────────────┐   │
│  │  2. QUERY REFORMULATION (if conversational)                  │   │
│  │     "What about the fee?" → "What is the cancellation fee?"  │   │
│  └──────────────────────┬───────────────────────────────────────┘   │
│                         │                                           │
│  ┌──────────────────────▼───────────────────────────────────────┐   │
│  │  3. HYBRID RETRIEVAL                                         │   │
│  │                                                              │   │
│  │  ┌─────────────────┐      ┌──────────────────────┐          │   │
│  │  │  Vector Search  │      │   Keyword Search     │          │   │
│  │  │  (ChromaDB /    │      │   (BM25 /            │          │   │
│  │  │   FAISS /       │      │    Elasticsearch)    │          │   │
│  │  │   Pinecone)     │      │                      │          │   │
│  │  └────────┬────────┘      └──────────┬───────────┘          │   │
│  │           │                          │                       │   │
│  │           └────────────┬─────────────┘                       │   │
│  │                        ▼                                     │   │
│  │              RRF Fusion (rank merge)                         │   │
│  └──────────────────────┬───────────────────────────────────────┘   │
│                         │                                           │
│  ┌──────────────────────▼───────────────────────────────────────┐   │
│  │  4. RERANKING                                                │   │
│  │     Cohere / CrossEncoder / FlashRank                        │   │
│  │     top-10 → top-5                                           │   │
│  └──────────────────────┬───────────────────────────────────────┘   │
│                         │                                           │
│  ┌──────────────────────▼───────────────────────────────────────┐   │
│  │  5. PROMPT CONSTRUCTION                                      │   │
│  │     System prompt + Few-shot examples + Context + Query      │   │
│  │     Strategy: Zero-shot / Few-shot / CoT / Role-specific     │   │
│  └──────────────────────┬───────────────────────────────────────┘   │
│                         │                                           │
│  ┌──────────────────────▼───────────────────────────────────────┐   │
│  │  6. LLM GENERATION                                           │   │
│  │     OpenAI GPT-4o / Anthropic Claude 3                       │   │
│  │     Sync / Async / Streaming                                 │   │
│  └──────────────────────┬───────────────────────────────────────┘   │
│                         │                                           │
│  ┌──────────────────────▼───────────────────────────────────────┐   │
│  │  7. POST-PROCESSING                                          │   │
│  │     Citation footer + Hallucination check + Save history     │   │
│  └──────────────────────┬───────────────────────────────────────┘   │
│                         │                                           │
└─────────────────────────┼───────────────────────────────────────────┘
                          │
                          ▼
                     Response + Sources
```

### Document Ingestion Pipeline

```
Raw Documents (PDF, DOCX, HTML, MD, TXT)
         │
         ▼
┌─────────────────────┐
│   DOCUMENT PARSER   │
│  Rule-based         │
│  AI-based (unstr.)  │
│  → ParsedDocument   │
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│      CHUNKER        │
│  Fixed / Sentence   │
│  Paragraph          │
│  Hierarchical  ←── recommended
│  Semantic           │
│  Sliding Window     │
│  → DocumentChunk[]  │
└────────┬────────────┘
         │
         ├──────────────────────────────────┐
         ▼                                  ▼
┌────────────────────┐           ┌────────────────────┐
│   VECTOR INDEX     │           │   KEYWORD INDEX    │
│  Embed chunks      │           │  Tokenize chunks   │
│  ChromaDB / FAISS  │           │  BM25 / Elastic    │
│  / Pinecone        │           │                    │
└────────────────────┘           └────────────────────┘
         │                                  │
         └──────────────┬───────────────────┘
                        ▼
                  HYBRID INDEX
                (Ready for search)
```

### Evaluation Framework

```
Test Dataset (question, context, answer, ground_truth)
                    │
                    ▼
        ┌───────────────────────┐
        │     RAG EVALUATOR     │
        │                       │
        │  LLM-Based Metrics    │
        │  ┌─────────────────┐  │
        │  │Context Relevance│  │
        │  │Faithfulness     │  │
        │  │Answer Relevance │  │
        │  │Answer Correct.  │  │
        │  └─────────────────┘  │
        │                       │
        │  Statistical Metrics  │
        │  ┌─────────────────┐  │
        │  │ROUGE-L          │  │
        │  │Context Recall   │  │
        │  │Citation Prec.   │  │
        │  │Answer Length    │  │
        │  └─────────────────┘  │
        └───────────┬───────────┘
                    │
                    ▼
           Evaluation Report
        (scores, pass rates, CSV)
```

---

## 📁 Project Structure

```
customer-support-chatbot/
│
├── 📁 configs/                    # Application configuration
│   ├── __init__.py
│   ├── settings.py                # Pydantic Settings — all env vars typed
│   └── logging_config.py          # Structlog — JSON prod / colored dev
│
├── 📁 data/
│   ├── raw/                       # Source documents (PDF, DOCX, etc.)
│   ├── processed/                 # Chunked JSONL files
│   ├── sample_docs/               # Sample FAQ and policy documents
│   └── eval/                      # Evaluation datasets and reports
│
├── 📁 migrations/                 # Alembic database migrations
│   ├── env.py
│   └── versions/
│       └── 001_initial.py         # Initial schema
│
├── 📁 models/                     # Fine-tuned LoRA adapters (git-ignored)
│
├── 📁 monitoring/
│   ├── prometheus.yml             # Prometheus scrape config
│   └── grafana/
│       └── dashboards/
│           ├── chatbot_dashboard.json
│           └── provisioning.yml
│
├── 📁 notebooks/
│   ├── 01_document_exploration.ipynb   # Chunking analysis
│   └── 02_evaluation_analysis.ipynb    # Metric visualization
│
├── 📁 scripts/
│   ├── ingest_documents.py        # CLI: parse → chunk → index
│   ├── build_index.py             # CLI: rebuild index from processed JSONL
│   ├── evaluate_pipeline.py       # CLI: run evaluation suite
│   └── finetune_adapter.py        # CLI: LoRA / QLoRA fine-tuning
│
├── 📁 src/
│   ├── __init__.py
│   │
│   ├── 📁 parsing/                # Document ingestion layer
│   │   ├── document_parser.py     # PDF/DOCX/HTML/MD parsers
│   │   └── chunking.py            # 6 chunking strategies
│   │
│   ├── 📁 indexing/               # Search index layer
│   │   ├── embeddings.py          # OpenAI + SentenceTransformer
│   │   ├── vector_store.py        # Chroma + FAISS + Pinecone
│   │   ├── keyword_index.py       # BM25 + Elasticsearch
│   │   └── hybrid_index.py        # RRF fusion
│   │
│   ├── 📁 retrieval/              # Retrieval layer
│   │   ├── retriever.py           # Orchestrates hybrid search
│   │   └── reranker.py            # Cohere + CrossEncoder + FlashRank
│   │
│   ├── 📁 generation/             # Generation layer
│   │   ├── llm_client.py          # OpenAI + Anthropic clients
│   │   ├── prompt_engine.py       # All prompt strategies
│   │   └── raft.py                # RAFT training data generation
│   │
│   ├── 📁 pipeline/               # Orchestration layer
│   │   ├── rag_pipeline.py        # End-to-end RAG pipeline
│   │   └── conversation.py        # Redis-backed session management
│   │
│   ├── 📁 evaluation/             # Evaluation layer
│   │   ├── metrics.py             # All metric implementations
│   │   └── evaluator.py           # Batch evaluation orchestrator
│   │
│   └── 📁 api/                    # API layer
│       ├── main.py                # FastAPI app + lifespan
│       ├── schemas.py             # Pydantic request/response models
│       ├── middleware.py          # Logging + rate limiting
│       └── routes/
│           ├── chat.py            # POST /chat, /feedback
│           ├── admin.py           # Documents, evaluation, stats
│           └── health.py          # /health, /ready, /live
│
├── 📁 tests/
│   ├── unit/                      # Fast, no I/O tests
│   │   ├── test_chunking.py
│   │   ├── test_rrf.py
│   │   ├── test_paragraph_chunker.py
│   │   ├── test_faiss_persistence.py
│   │   └── test_async_streaming.py
│   ├── integration/               # Tests with mocked LLM
│   │   └── test_rag_pipeline.py
│   └── e2e/                       # Full stack tests
│       └── test_api_e2e.py
│
├── 📁 .github/
│   └── workflows/
│       └── ci.yml                 # Lint → Test → Docker build
│
├── .env.example                   # Environment variable template
├── alembic.ini                    # Database migration config
├── docker-compose.yml             # Full 7-service stack
├── Dockerfile                     # Multi-stage production build
├── Makefile                       # Developer convenience commands
├── pyproject.toml                 # Project metadata + tool config
└── requirements.txt               # All Python dependencies
```

---

## 📦 Prerequisites

### Required

| Dependency | Version | Purpose |
|---|---|---|
| Python | 3.11+ | Runtime |
| Docker | 24.0+ | Container runtime |
| Docker Compose | 2.20+ | Multi-service orchestration |

### API Keys (at least one LLM provider required)

| Service | Required | Purpose |
|---|---|---|
| OpenAI | ✅ Recommended | GPT-4o for generation + embeddings |
| Anthropic | Optional | Claude 3 alternative |
| Cohere | Optional | Best-in-class reranking |

### Optional External Services

| Service | Default | Alternative |
|---|---|---|
| Vector Store | ChromaDB (local) | Pinecone (cloud) or FAISS (disk) |
| Keyword Search | BM25 (in-memory) | Elasticsearch (Docker) |
| Conversation Store | Redis (Docker) | In-memory fallback |
| Database | PostgreSQL (Docker) | SQLite for dev |

---

## 🚀 Quick Start

### Option A: Docker (Recommended — Full Stack)

```bash
# 1. Clone the repository
git clone https://github.com/AdilShamim8/Customer-Support-Chatbot-102.git
cd customer-support-chatbot

# 2. Configure environment
cp .env.example .env

# Edit .env — minimum required:
# OPENAI_API_KEY=sk-...
nano .env

# 3. Start all services
make up
# or: docker-compose up -d

# 4. Wait for services to be healthy (~30 seconds)
docker-compose ps

# 5. Add your documents
cp your-docs/*.pdf data/raw/
make ingest

# 6. Test the API
curl -X POST http://localhost:8000/api/v1/chat/ \
  -H "Content-Type: application/json" \
  -d '{"message": "What is your return policy?"}'

# 7. Open API docs
open http://localhost:8000/docs

# 8. View monitoring dashboards
open http://localhost:3000   # Grafana (admin/admin)
open http://localhost:9090   # Prometheus
```

### Option B: Local Development (No Docker)

```bash
# 1. Clone and set up Python environment
git clone https://github.com/AdilShamim8/Customer-Support-Chatbot-102.git
cd customer-support-chatbot

python -m venv venv
source venv/bin/activate         # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt
python -m nltk.downloader punkt stopwords

# 3. Configure environment
cp .env.example .env
# Set OPENAI_API_KEY and APP_ENV=development
nano .env

# 4. Add sample documents and ingest
# (uses in-memory BM25 + local ChromaDB — no external services needed)
python scripts/ingest_documents.py \
    --source-dir ./data/sample_docs \
    --chunk-strategy hierarchical

# 5. Start the API server
make dev
# or: uvicorn src.api.main:app --reload --port 8000

# 6. Test
curl -X POST http://localhost:8000/api/v1/chat/ \
  -H "Content-Type: application/json" \
  -d '{"message": "How do I reset my password?"}'
```

### Verify Installation

```bash
# Health check
curl http://localhost:8000/health

# Expected response:
{
  "status": "healthy",
  "version": "1.0.0",
  "components": {
    "rag_pipeline": "healthy",
    "vector_store": "healthy (142 chunks)",
    "redis": "healthy",
    "llm_client": "healthy (OpenAIClient)"
  },
  "uptime_seconds": 23.4
}
```

---

## ⚙️ Configuration

All configuration is via environment variables. Copy `.env.example` to `.env`
and fill in your values.

### Core Settings

```env
# ── Application ──────────────────────────────────────────────────────
APP_ENV=development          # development | staging | production
LOG_LEVEL=INFO               # DEBUG | INFO | WARNING | ERROR
SECRET_KEY=your-secret-key
API_RATE_LIMIT=100           # requests per minute per IP

# ── LLM Provider ─────────────────────────────────────────────────────
LLM_PROVIDER=openai          # openai | anthropic
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-... # optional
COHERE_API_KEY=...           # optional (for reranking)

# ── Models ───────────────────────────────────────────────────────────
CHAT_MODEL=gpt-4o
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIMENSION=1536
RERANKER_MODEL=rerank-english-v3.0

# ── Vector Store ─────────────────────────────────────────────────────
VECTOR_STORE_TYPE=chroma     # chroma | faiss | pinecone
CHROMA_HOST=localhost
CHROMA_PORT=8000
CHROMA_COLLECTION=support_docs

# For Pinecone:
PINECONE_API_KEY=...
PINECONE_ENVIRONMENT=us-east-1-aws
PINECONE_INDEX_NAME=customer-support

# ── Search ───────────────────────────────────────────────────────────
ELASTICSEARCH_URL=http://localhost:9200
ELASTICSEARCH_USER=elastic
ELASTICSEARCH_PASSWORD=changeme

# ── Storage ──────────────────────────────────────────────────────────
REDIS_URL=redis://localhost:6379/0
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/chatbot_db

# ── RAG Parameters ───────────────────────────────────────────────────
TOP_K_RETRIEVAL=10           # candidates from hybrid search
TOP_K_RERANK=5               # final chunks after reranking
SIMILARITY_THRESHOLD=0.7     # minimum relevance score
MAX_CONTEXT_TOKENS=4096      # context window budget
MAX_RESPONSE_TOKENS=1024     # generation limit

# ── Chunking ─────────────────────────────────────────────────────────
CHUNK_SIZE=512
CHUNK_OVERLAP=64
MIN_CHUNK_SIZE=100

# ── Conversation ─────────────────────────────────────────────────────
MAX_CONVERSATION_TURNS=20
CONVERSATION_TTL_SECONDS=3600
```

### Selecting a Vector Store

```bash
# Local development (default, no setup needed)
VECTOR_STORE_TYPE=chroma

# High-performance in-memory/disk (no external service)
VECTOR_STORE_TYPE=faiss

# Cloud-scale production
VECTOR_STORE_TYPE=pinecone
PINECONE_API_KEY=your-key
PINECONE_ENVIRONMENT=us-east-1-aws
```

### Selecting a Reranker

```bash
# Best quality (requires Cohere API key)
COHERE_API_KEY=your-key       # → CohereReranker auto-selected

# Local cross-encoder (no API, requires GPU/CPU)
# Set COHERE_API_KEY empty → FlashRankReranker auto-selected
```

---

## 📄 Document Ingestion

### Supported Formats

| Format | Parser | Notes |
|---|---|---|
| PDF | pdfplumber (rule) / unstructured (AI) | Best with AI parser for complex layouts |
| DOCX | python-docx | Preserves heading hierarchy |
| HTML | BeautifulSoup | Strips nav/footer/scripts |
| Markdown | Custom regex | Preserves heading structure |
| TXT | Direct read | Plain text fallback |

### Ingestion Command

```bash
# Ingest all documents in a directory
python scripts/ingest_documents.py \
    --source-dir ./data/raw \
    --chunk-strategy hierarchical \
    --parse-strategy rule_based \
    --chunk-size 512 \
    --chunk-overlap 64

# Arguments:
#   --source-dir         Directory containing source documents
#   --chunk-strategy     fixed_size | sentence | paragraph |
#                        hierarchical | semantic | sliding_window
#   --parse-strategy     rule_based | ai_based
#   --chunk-size         Target chunk size in characters
#   --chunk-overlap      Overlap between consecutive chunks
#   --dry-run            Parse without indexing (for testing)
```

### Chunking Strategy Guide

```
Strategy         When to Use                          Trade-off
─────────────────────────────────────────────────────────────────────
fixed_size       Simple docs, uniform content         Fast, may split mid-sentence
sentence         Conversational content, FAQs         Better coherence, slower
paragraph        Policy docs, structured text         Natural boundaries
hierarchical     Long docs with headings ← recommended Best recall + context
semantic         Mixed content, research docs         Best coherence, needs GPU
sliding_window   Dense technical docs                 High recall, more chunks
```

### Via API (Upload)

```bash
# Upload a single document
curl -X POST http://localhost:8000/api/v1/admin/documents/upload \
  -F "file=@./data/raw/refund_policy.pdf" \
  -F "chunk_strategy=hierarchical" \
  -F "parse_strategy=rule_based"

# Response:
{
  "status": "processing",
  "filename": "refund_policy.pdf",
  "message": "Document is being indexed in the background"
}

# Delete a document by ID
curl -X DELETE http://localhost:8000/api/v1/admin/documents/doc_abc123
```

### Rebuild Index

```bash
# Rebuild the entire index from processed JSONL files
python scripts/build_index.py \
    --processed-dir ./data/processed \
    --store-type chroma \
    --embedding-model text-embedding-3-small \
    --clear   # wipe and rebuild from scratch
```

---

## 🧠 Prompt Engineering

This system implements **five prompt strategies** selectable per-request.

### Strategy Overview

#### 1. Zero-Shot (`zero_shot`)
Direct answer from context. No examples. Fastest and most concise.

```
System: "Answer using ONLY the provided context. If unknown, say so."
Context: [retrieved docs]
User: "What is your return policy?"
```

**Best for**: Simple factual questions with clear answers in documentation.

#### 2. Few-Shot (`few_shot`)
Includes 2 demonstration Q&A examples before the actual question.
Guides format, tone, and structure.

```
System: [support agent persona]
[Example 1: password reset Q&A]
[Example 2: billing dispute Q&A]
Context: [retrieved docs]
User: "What is your return policy?"
```

**Best for**: Consistent formatting, tone matching, structured responses.

#### 3. Chain-of-Thought (`chain_of_thought`)
Model reasons step-by-step before answering. Shows its work.

```
System: "Think step by step: 1) What is the problem? 
         2) What does context say? 3) What is the best response?"
Context: [retrieved docs]
User: "My order is missing."
→ "Let me think through this...
   Step 1: Customer hasn't received their order.
   Step 2: Context says wait 24h then file claim within 7 days.
   Step 3: Recommend immediate actions + claim process.
   Answer: ..."
```

**Best for**: Complex multi-step issues, troubleshooting, edge cases.

#### 4. Role-Specific (`role_specific`)
Specialized system prompts per department (billing, technical, general).
User tier and history injected into system prompt.

```
System: "You are a billing specialist for AcmeCorp.
         Customer: Jane Doe (Premium tier, customer since 2021)
         Open tickets: 0. Recent purchases: Pro Plan"
```

**Best for**: Tiered support, department routing, VIP customers.

#### 5. RAG Standard (`rag_standard`) ← Default
Balanced combination: role persona + few-shot examples + context.

**Best for**: General production use.

### Selecting a Strategy Per Request

```bash
curl -X POST http://localhost:8000/api/v1/chat/ \
  -H "Content-Type: application/json" \
  -d '{
    "message": "My order is missing",
    "prompt_strategy": "chain_of_thought",
    "user_context": {
      "customer_name": "Alice Johnson",
      "account_tier": "premium",
      "technical_level": "beginner"
    }
  }'
```

---

## 🔄 RAG Pipeline

### Full Flow Explained

```
1. QUERY REFORMULATION
   ────────────────────
   "What about the fee?"  →  "What is the cancellation fee for Pro Plan?"
   
   Conversational follow-ups are rephrased as standalone questions
   so the retriever can find relevant documents without context.

2. HYBRID RETRIEVAL
   ─────────────────
   Query → Embed → Vector Search (semantic similarity)
         → Tokenize → BM25 Search (keyword matching)
         → RRF Fusion (merge + rerank by combined rank)

   Example: "password reset email not received"
   Vector finds: semantically similar password docs
   BM25 finds: exact matches for "password reset email"
   RRF: combines both for best coverage

3. RERANKING
   ──────────
   10 candidates → Cross-encoder scores each (query, chunk) pair → top 5
   
   Why? Bi-encoders embed query and doc independently (fast, less precise).
   Cross-encoders see query+doc together (slow, highly precise).
   Retrieve many → rerank few = best of both.

4. CONTEXT ASSEMBLY
   ─────────────────
   [Source 1: Refund Policy — Returns Section] (relevance: 0.94)
   Items can be returned within 30 days...
   
   [Source 2: FAQ — Billing] (relevance: 0.87)
   Digital products are non-refundable...

5. PROMPT CONSTRUCTION
   ────────────────────
   System prompt + few-shot examples + assembled context + user query
   Token budget managed: context truncated if approaching limit.

6. GENERATION + CITATION
   ───────────────────────
   Answer generated → source footer appended:
   
   "We offer a 30-day return policy on physical items..."
   
   ---
   Sources:
   1. Refund Policy (pdf)
   2. FAQ — Billing (html)
```

### Multi-Turn Conversations

```bash
# Turn 1 — creates session
curl -X POST http://localhost:8000/api/v1/chat/ \
  -d '{"message": "What is your refund policy?",
       "conversation_id": "session-abc123"}'

# Turn 2 — follow-up uses history
curl -X POST http://localhost:8000/api/v1/chat/ \
  -d '{"message": "What about digital products?",
       "conversation_id": "session-abc123"}'
# → "What about digital products?" is reformulated to
# → "What is the refund policy for digital products?"
# → before retrieval

# Clear session
curl -X DELETE http://localhost:8000/api/v1/chat/session-abc123
```

### Streaming Responses

```bash
# Server-Sent Events (SSE) streaming
curl -X POST http://localhost:8000/api/v1/chat/ \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{"message": "Explain your cancellation policy", "stream": true}'

# Output (token by token):
# data: We
# data:  offer
# data:  a
# data:  30-day
# ...
# data: [DONE]
```

---

## 🎯 Fine-Tuning with PEFT/LoRA

### Overview

Fine-tuning adapts an open-source model (Mistral, LLaMA, etc.) to:
- Follow your company's tone and response style
- Cite sources using `##begin_quote##` markers (RAFT training)
- Ignore distractor documents and focus on relevant content
- Reduce hallucination in domain-specific contexts

### Step 1: Generate RAFT Training Data

RAFT (Retrieval Augmented Fine-Tuning) creates training examples where
the model learns to identify which documents are relevant and which are
distractors.

```bash
python scripts/finetune_adapter.py \
    --base-model mistralai/Mistral-7B-Instruct-v0.2 \
    --dataset ./data/raft/train.jsonl \
    --output ./models/support-lora \
    --generate-raft-data   # generates dataset from your index first
```

**RAFT data format (auto-generated)**:
```json
{
  "messages": [
    {
      "role": "system",
      "content": "You are a support agent. Documents: [oracle + distractors]"
    },
    {"role": "user", "content": "How do I cancel my subscription?"},
    {
      "role": "assistant",
      "content": "Let me check the relevant document...\n
                  According to Document [2]: ##begin_quote## 
                  Subscriptions can be cancelled at any time 
                  ##end_quote##\n\nYou can cancel by going to..."
    }
  ]
}
```

### Step 2: Fine-Tune with LoRA or QLoRA

```bash
# QLoRA — runs on single GPU with 16GB VRAM (recommended)
python scripts/finetune_adapter.py \
    --base-model mistralai/Mistral-7B-Instruct-v0.2 \
    --dataset ./data/raft/train.jsonl \
    --output ./models/support-lora \
    --method qlora \
    --lora-r 16 \
    --epochs 3 \
    --batch-size 4

# LoRA — full precision, requires more VRAM
python scripts/finetune_adapter.py \
    --method lora \
    --lora-r 32 \
    --epochs 5
```

### LoRA Rank Selection Guide

```
rank (r)   Parameters Added    Quality    Speed
────────────────────────────────────────────────
4          ~1M                 Good       Fastest
8          ~2M                 Better     Fast
16         ~4M   ← recommended Excellent  Good
32         ~8M                 Best       Slower
64         ~16M                Marginal+  Slowest
```

### Step 3: Merge Adapter for Inference

```bash
# Merge LoRA weights into base model (zero inference overhead)
python scripts/finetune_adapter.py \
    --base-model mistralai/Mistral-7B-Instruct-v0.2 \
    --dataset ./data/raft/train.jsonl \
    --output ./models/support-lora \
    --merge   # creates ./models/support-lora-merged/
```

### Step 4: Use Fine-Tuned Model

```env
# In .env — point to local merged model
LLM_PROVIDER=local
CHAT_MODEL=./models/support-lora-merged
```

---

## 📡 API Reference

### Base URL
```
http://localhost:8000/api/v1
```

### Authentication
```
# Add to .env for production:
SECRET_KEY=your-secret-key

# Pass in header:
Authorization: Bearer your-api-key
```

### `POST /chat/` — Send Message

```bash
curl -X POST http://localhost:8000/api/v1/chat/ \
  -H "Content-Type: application/json" \
  -d '{
    "message": "How do I reset my password?",
    "conversation_id": "optional-session-id",
    "stream": false,
    "prompt_strategy": "rag_standard",
    "filters": {"doc_type": "pdf"},
    "user_context": {
      "customer_name": "Alice Johnson",
      "account_tier": "premium",
      "technical_level": "beginner",
      "preferred_language": "en",
      "open_tickets": 0,
      "recent_purchases": ["Pro Plan"]
    }
  }'
```

**Response:**
```json
{
  "answer": "To reset your password:\n\n1. Go to the login page\n2. Click **Forgot Password**\n3. Enter your email...\n\n---\n**Sources:**\n1. Account Management Guide (pdf)",
  "conversation_id": "conv-abc123",
  "sources": [
    {
      "doc_id": "doc_001",
      "title": "Account Management Guide",
      "source": "docs/account.pdf",
      "doc_type": "pdf"
    }
  ],
  "confidence": 0.9234,
  "reformulated_query": null,
  "metadata": {
    "latency_ms": 1243.5,
    "tokens_used": 1823,
    "cost_usd": 0.000456,
    "retrieval_count": 5
  }
}
```

### `POST /chat/feedback` — Submit Feedback

```bash
curl -X POST http://localhost:8000/api/v1/chat/feedback \
  -d '{
    "conversation_id": "conv-abc123",
    "message_index": 0,
    "rating": 5,
    "was_helpful": true,
    "feedback_text": "Very clear and accurate!",
    "issue_category": "account"
  }'
```

### `DELETE /chat/{conversation_id}` — Clear Session

```bash
curl -X DELETE http://localhost:8000/api/v1/chat/conv-abc123
```

### `POST /admin/documents/upload` — Upload Document

```bash
curl -X POST http://localhost:8000/api/v1/admin/documents/upload \
  -F "file=@policy.pdf" \
  -F "chunk_strategy=hierarchical" \
  -F "parse_strategy=rule_based"
```

### `DELETE /admin/documents/{doc_id}` — Remove Document

```bash
curl -X DELETE http://localhost:8000/api/v1/admin/documents/doc_abc123
```

### `POST /admin/evaluate` — Run Evaluation

```bash
curl -X POST http://localhost:8000/api/v1/admin/evaluate \
  -d '{
    "samples": [
      {
        "question": "What is the return policy?",
        "answer": "30-day returns on physical items.",
        "contexts": ["Items can be returned within 30 days."],
        "ground_truth": "30-day money back on physical items."
      }
    ],
    "dataset_name": "manual_eval",
    "use_llm_metrics": true,
    "use_statistical_metrics": true
  }'
```

### `GET /admin/stats` — Pipeline Statistics

```bash
curl http://localhost:8000/api/v1/admin/stats
```

**Response:**
```json
{
  "vector_store_count": 1842,
  "keyword_index_count": 1842,
  "document_count": 47,
  "llm_requests": 1293,
  "total_tokens_used": 2847291,
  "total_cost_usd": 14.23
}
```

### `GET /health` — Health Check

```bash
curl http://localhost:8000/health
```

### `GET /metrics` — Prometheus Metrics

```bash
curl http://localhost:8000/metrics
```

---

## 📊 Evaluation

### Running Evaluation

```bash
# CLI evaluation against test dataset
python scripts/evaluate_pipeline.py \
    --dataset ./data/eval/test_set.jsonl \
    --output ./data/eval/report.json \
    --max-samples 100

# Without LLM metrics (fast, no API calls)
python scripts/evaluate_pipeline.py \
    --no-llm-metrics

# Via Makefile
make evaluate
```

### Test Dataset Format (`test_set.jsonl`)

```jsonl
{"question": "How do I cancel?", "ground_truth": "Go to Settings > Cancel."}
{"question": "What is the refund window?", "ground_truth": "30 days."}
```

### Understanding Metrics

| Metric | What It Measures | Target |
|---|---|---|
| **Context Relevance** | Are retrieved docs relevant to query? | ≥ 0.75 |
| **Faithfulness** | Is answer grounded in context? | ≥ 0.85 |
| **Answer Relevance** | Does answer address the question? | ≥ 0.80 |
| **Answer Correctness** | Factual accuracy vs. ground truth | ≥ 0.75 |
| **Context Recall** | Token overlap: answer ∩ context | ≥ 0.60 |
| **ROUGE-L** | Lexical overlap with ground truth | ≥ 0.30 |
| **Citation Precision** | Are sources cited in answer? | ≥ 0.70 |
| **Answer Length** | Word count in acceptable range | 20–500 |

### Sample Report Output

```
════════════════════════════════════════════════════════════
  RAG EVALUATION REPORT: production_eval
════════════════════════════════════════════════════════════
  Total Samples:     150
  Overall Pass Rate: 87.3%
  Evaluation Time:   243.1s

  Metric Scores:
  ──────────────────────────────────────────────────────────
  ✅ faithfulness               avg=0.891 ± 0.087  pass=91.3%
  ✅ answer_relevance           avg=0.873 ± 0.094  pass=88.7%
  ✅ context_relevance          avg=0.812 ± 0.121  pass=84.0%
  ✅ answer_correctness         avg=0.798 ± 0.132  pass=82.0%
  ⚠️  context_recall            avg=0.681 ± 0.156  pass=71.3%
  ✅ rouge                      avg=0.412 ± 0.189  pass=79.3%
  ✅ citation_precision         avg=0.834 ± 0.097  pass=87.3%
  ✅ answer_length              avg=0.943 ± 0.067  pass=94.7%
════════════════════════════════════════════════════════════
```

### Improving Low Scores

```
Low Context Relevance?
  → Try hierarchical chunking (better section context)
  → Increase TOP_K_RETRIEVAL
  → Check document quality

Low Faithfulness?
  → Enable hallucination check (CHECK_HALLUCINATION=true)
  → Reduce SIMILARITY_THRESHOLD to retrieve better docs
  → Fine-tune with RAFT data

Low Answer Correctness?
  → Add more documents covering the topic
  → Increase TOP_K_RERANK for more context
  → Use CoT prompting for complex questions

Low Context Recall?
  → Increase chunk overlap (CHUNK_OVERLAP=128)
  → Use sliding_window chunking
  → Increase TOP_K_RETRIEVAL
```

---

## 📈 Monitoring

### Grafana Dashboard

```bash
open http://localhost:3000
# Login: admin / admin (change in production via GRAFANA_PASSWORD)
```

**Panels included:**
- Request rate (req/s)
- P50 / P95 / P99 latency
- Error rate
- LLM token usage over time
- Retrieval score distribution
- Active conversations
- Cost per hour

### Key Prometheus Metrics

```promql
# Request rate
rate(http_requests_total{job="chatbot"}[5m])

# P95 latency
histogram_quantile(0.95,
  rate(http_request_duration_seconds_bucket{job="chatbot"}[5m])
) * 1000

# Error rate
rate(http_requests_total{job="chatbot", status=~"5.."}[5m])
/ rate(http_requests_total{job="chatbot"}[5m])

# Requests by endpoint
sum by (handler)(rate(http_requests_total{job="chatbot"}[5m]))
```

### Structured Log Fields

Every log line in production (JSON format) includes:

```json
{
  "timestamp": "2024-01-15T10:23:41.123Z",
  "level": "info",
  "logger": "src.pipeline.rag_pipeline",
  "event": "RAG query complete",
  "app": "customer-support-chatbot",
  "env": "production",
  "request_id": "a3f2b1c9",
  "latency_ms": 1243.5,
  "sources": 3,
  "tokens": 1823,
  "cost": "$0.000456"
}
```

---

## 🚢 Deployment

### Production Checklist

```bash
# 1. Set production environment variables
APP_ENV=production
LOG_LEVEL=INFO
SECRET_KEY=<cryptographically-random-32-bytes>
API_RATE_LIMIT=60

# 2. Use production LLM models
CHAT_MODEL=gpt-4o
EMBEDDING_MODEL=text-embedding-3-small

# 3. Use cloud vector store for scale
VECTOR_STORE_TYPE=pinecone

# 4. Disable debug endpoints
# (docs_url and redoc_url auto-disabled in production)

# 5. Set strong passwords
POSTGRES_PASSWORD=<strong-password>
GRAFANA_PASSWORD=<strong-password>
ELASTIC_PASSWORD=<strong-password>
```

### Deploy with Docker Compose

```bash
# Production deployment
docker-compose -f docker-compose.yml up -d

# Scale API workers
docker-compose up -d --scale chatbot=3

# View logs
docker-compose logs -f chatbot

# Rolling update
docker-compose pull chatbot
docker-compose up -d --no-deps chatbot
```

### Kubernetes (Helm)

```bash
# Coming soon — see /k8s directory for manifests
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/ingress.yaml

# Check probes
GET /ready   # Kubernetes readiness probe
GET /live    # Kubernetes liveness probe
```

### Database Migrations

```bash
# Run migrations before starting the app in production
alembic upgrade head

# Create a new migration
alembic revision --autogenerate -m "add_user_preferences_table"

# Rollback one version
alembic downgrade -1
```

---

## 🧪 Testing

### Run All Tests

```bash
# Full test suite
make test

# Unit tests only (fast, no I/O)
make test-unit

# Integration tests (mocked LLM)
make test-integration

# E2E tests (requires running app)
make up
pytest tests/e2e/ --base-url http://localhost:8000 -v
```

### Test Coverage

```bash
pytest tests/unit/ tests/integration/ \
  --cov=src \
  --cov-report=html \
  --cov-report=term-missing

open htmlcov/index.html
```

### Writing Tests

```python
# Unit test pattern (no external calls)
def test_my_component():
    chunker = ChunkerFactory.get_chunker(ChunkingStrategy.PARAGRAPH)
    doc = make_doc("Para one.\n\nPara two.")
    chunks = chunker.chunk(doc)
    assert len(chunks) >= 1

# Integration test pattern (mock LLM)
@pytest.mark.asyncio
async def test_pipeline(mock_pipeline):
    response = await mock_pipeline.aquery("How do I reset my password?")
    assert response.answer
    assert len(response.sources) > 0

# E2E test pattern (real HTTP)
def test_chat_endpoint(client):
    r = client.post("/api/v1/chat/", json={"message": "Hello"})
    assert r.status_code == 200
    assert r.json()["answer"]
```

---

## ⚡ Performance

### Benchmarks (GPT-4o, local ChromaDB, 1842 chunks)

| Metric | Value |
|---|---|
| P50 latency (with reranking) | ~1.1s |
| P95 latency (with reranking) | ~2.3s |
| P50 latency (no reranking) | ~0.7s |
| Throughput | ~45 req/s (4 workers) |
| Vector search (10K chunks) | ~15ms |
| BM25 search (10K chunks) | ~5ms |
| Cohere reranking (10→5) | ~180ms |
| FlashRank reranking (10→5) | ~12ms |

### Optimization Tips

```bash
# 1. Use FlashRank instead of Cohere for lower latency
# (no API call, runs locally)
COHERE_API_KEY=   # leave empty → FlashRank selected

# 2. Reduce retrieval candidates
TOP_K_RETRIEVAL=6   # from 10
TOP_K_RERANK=3      # from 5

# 3. Use faster embedding model
EMBEDDING_MODEL=text-embedding-3-small   # vs large

# 4. Use GPT-4o-mini for non-critical queries
CHAT_MODEL=gpt-4o-mini   # 10x cheaper, 2x faster

# 5. Enable Redis caching (already in docker-compose)
REDIS_URL=redis://localhost:6379/0

# 6. Use FAISS for vector search (no network overhead)
VECTOR_STORE_TYPE=faiss
```

---

## 🔧 Troubleshooting

### Common Issues

#### `OPENAI_API_KEY not set`
```bash
# Check .env file exists and has the key
cat .env | grep OPENAI_API_KEY

# Reload environment
source .env
```

#### `ChromaDB connection refused`
```bash
# Check if ChromaDB container is running
docker-compose ps chromadb

# Restart it
docker-compose restart chromadb

# For local dev, use in-memory (no external service needed)
VECTOR_STORE_TYPE=faiss
```

#### `Redis connection failed`
```bash
# The app falls back to in-memory automatically
# For Docker:
docker-compose restart redis

# Verify
redis-cli -u redis://localhost:6379 ping
# → PONG
```

#### `Empty retrieval results`
```bash
# Check index has documents
curl http://localhost:8000/api/v1/admin/stats
# → vector_store_count should be > 0

# If 0, run ingestion:
make ingest
```

#### `Hallucinated answers`
```bash
# Enable hallucination check
# In src/api/main.py, set:
check_hallucination=True

# Or lower similarity threshold (retrieve better docs)
SIMILARITY_THRESHOLD=0.6

# Increase context
TOP_K_RERANK=7
```

#### `Fine-tuning OOM (Out of Memory)`
```bash
# Use QLoRA with lower rank
python scripts/finetune_adapter.py \
    --method qlora \
    --lora-r 8 \          # reduce from 16
    --batch-size 1 \      # reduce batch size
    --max-seq-length 1024  # reduce sequence length
```

### Debug Mode

```bash
# Enable verbose logging
LOG_LEVEL=DEBUG make dev

# Inspect specific request
curl http://localhost:8000/api/v1/chat/ \
  -d '{"message": "test"}' \
  -v 2>&1 | grep -E "X-Request-ID|X-Response-Time"
```

---

## 🤝 Contributing

We welcome contributions! Please follow these steps:

### Development Setup

```bash
git clone https://github.com/yourorg/customer-support-chatbot.git
cd customer-support-chatbot
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
pre-commit install
```

### Code Standards

```bash
# Format
make format      # runs black + isort

# Lint
make lint        # runs flake8 + mypy

# Test
make test        # runs full test suite

# All checks (required before PR)
make format lint test
```

### Pull Request Guidelines

1. **Branch naming**: `feature/`, `fix/`, `docs/`, `refactor/`
2. **Commit messages**: Follow [Conventional Commits](https://www.conventionalcommits.org/)
   ```
   feat: add semantic chunking strategy
   fix: resolve FAISS persistence bug
   docs: update chunking strategy guide
   ```
3. **Test coverage**: New code must have ≥ 80% test coverage
4. **Type hints**: All public functions must be fully typed
5. **Docstrings**: All public classes and methods require docstrings

### Adding a New Chunking Strategy

```python
# 1. Add to ChunkingStrategy enum in chunking.py
class ChunkingStrategy(str, Enum):
    MY_STRATEGY = "my_strategy"

# 2. Implement the class
class MyChunker(BaseChunker):
    def chunk(self, document: ParsedDocument) -> list[DocumentChunk]:
        # your implementation
        ...

# 3. Register in ChunkerFactory._CHUNKERS
_CHUNKERS = {
    ChunkingStrategy.MY_STRATEGY: MyChunker,
    # ...
}

# 4. Add tests in tests/unit/test_chunking.py
# 5. Update this README under Chunking Strategy Guide
```

### Adding a New LLM Provider

```python
# 1. Add to LLMProvider enum in settings.py
class LLMProvider(str, Enum):
    MY_PROVIDER = "my_provider"

# 2. Implement client in llm_client.py
class MyProviderClient(BaseLLMClient):
    def complete(self, request: LLMRequest) -> LLMResponse: ...
    async def acomplete(self, request: LLMRequest) -> LLMResponse: ...
    def stream(self, request: LLMRequest) -> Iterator[str]: ...
    async def astream(self, request: LLMRequest) -> AsyncIterator[str]: ...

# 3. Register in LLMClientFactory.create()
# 4. Add API key to settings.py and .env.example
# 5. Add pricing to PRICING dict in llm_client.py
```

---

## 📚 Documentation

| Resource | Location |
|---|---|
| API Reference (Interactive) | http://localhost:8000/docs |
| API Reference (ReDoc) | http://localhost:8000/redoc |
| Document Exploration Notebook | `notebooks/01_document_exploration.ipynb` |
| Evaluation Analysis Notebook | `notebooks/02_evaluation_analysis.ipynb` |
| Architecture Diagram | `docs/assets/architecture.png` |

---

## 🔬 Research & References

This system implements techniques from the following papers:

| Paper | Application |
|---|---|
| [RAFT: Adapting Language Model to Domain Specific RAG](https://arxiv.org/abs/2403.10131) | Fine-tuning strategy |
| [Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks](https://arxiv.org/abs/2005.11401) | RAG foundation |
| [Reciprocal Rank Fusion outperforms Condorcet and individual Rank Learning Methods](https://dl.acm.org/doi/10.1145/1571941.1572114) | Hybrid search fusion |
| [LoRA: Low-Rank Adaptation of Large Language Models](https://arxiv.org/abs/2106.09685) | Parameter-efficient fine-tuning |
| [QLoRA: Efficient Finetuning of Quantized LLMs](https://arxiv.org/abs/2305.14314) | Memory-efficient training |
| [RAGAS: Automated Evaluation of RAG](https://arxiv.org/abs/2309.15217) | Evaluation framework |
| [Lost in the Middle](https://arxiv.org/abs/2307.03172) | Context positioning insight |

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## Contact

- Website: [Adil Shamim](https://adilshamim.me/)
- GitHub: [Adil Shamim](https://github.com/AdilShamim8)
- Create an issue in this repository for questions or suggestions

---

<p align="center">
  <a href="https://github.com/AdilShamim8">
    <img src="https://img.shields.io/badge/GitHub-AdilShamim8-181717?style=for-the-badge&logo=github&logoColor=white" alt="GitHub Profile"/>
  </a>
  <span style="opacity:.6">&nbsp;</span>

  <a href="https://www.linkedin.com/in/adilshamim8">
    <img src="https://img.shields.io/badge/LinkedIn-AdilShamim8-0A66C2?style=for-the-badge&logo=linkedin&logoColor=white" alt="LinkedIn Profile"/>
  </a>
  <span style="opacity:.6">&nbsp;</span>

  <a href="https://www.kaggle.com/adilshamim8">
    <img src="https://img.shields.io/badge/Kaggle-AdilShamim8-20BEFF?style=for-the-badge&logo=kaggle&logoColor=white" alt="Kaggle Profile"/>
  </a>
  <span style="opacity:.6">&nbsp;</span>

  <a href="https://x.com/adil_shamim8">
    <img src="https://img.shields.io/badge/Twitter%2FX-@adil__shamim8-000000?style=for-the-badge&logo=x&logoColor=white" alt="Twitter/X Profile"/>
  </a>
  <span style="opacity:.6">&nbsp;</span>

  <a href="https://adilshamim8.medium.com/">
    <img src="https://img.shields.io/badge/Medium-AdilShamim8-12100E?style=for-the-badge&logo=medium&logoColor=white" alt="Medium Profile"/>
  </a>
</p>
<div align="center">
  
⭐ **If you find this repository helpful, please consider giving it a star!** ⭐

</div>
