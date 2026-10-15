# ── Stage 1: Builder ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Stage 2: Runtime ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# OCI standard labels - image traceability in registries and runtimes
LABEL org.opencontainers.image.title="customer-support-chatbot" \
      org.opencontainers.image.description="Production RAG-based customer support chatbot" \
      org.opencontainers.image.authors="Adil Shamim" \
      org.opencontainers.image.url="https://github.com/AdilShamim8/Customer-Support-Chatbot-102" \
      org.opencontainers.image.source="https://github.com/AdilShamim8/Customer-Support-Chatbot-102" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.base.name="docker.io/library/python:3.11-slim"

WORKDIR /app

# Install runtime system dependencies
RUN apt-get update && apt-get install -y \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Create non-root user
RUN useradd -m -u 1000 appuser && \
    mkdir -p /app/data/chroma /app/data/raw /app/logs && \
    chown -R appuser:appuser /app

# Copy application code
COPY --chown=appuser:appuser . .

USER appuser

# Health check: /live is the CONTAINER liveness contract (no dependency
# checks - a Redis blip must not restart healthy pods; that is /ready's job)
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD curl -f http://localhost:8000/live || exit 1

EXPOSE 8000

# Production entrypoint: gunicorn with the tuned profile (SSE-aware
# timeouts, worker recycling). Override for dev: --entrypoint uvicorn ...
CMD ["gunicorn", "src.api.main:app", "--config", "gunicorn.conf.py"]