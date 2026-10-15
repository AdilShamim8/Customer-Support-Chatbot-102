"""
Gunicorn production configuration for the FastAPI application.

Sizing rationale (see docs/architecture/capacity-planning.md):
- Worker count = CPU cores * 2 + 1 is the *classic* formula, but this service
  is I/O-bound (LLM + vector store calls dominate latency), so we prefer a
  fixed floor with env override. Per-pod concurrency is intentionally low:
  horizontal pods (HPA) scale better than vertical worker counts for a
  100M+ MAU traffic profile with long-lived SSE streams.
- Uvicorn workers (not gthread) preserve full ASGI/SSE support.
- Graceful timeout must exceed the longest LLM stream (kept here at 120s to
  survive 99th-percentile generation) so in-flight answers drain before the
  pod is replaced during deploys.
"""

import multiprocessing
import os

bind = f"0.0.0.0:{os.getenv('PORT', '8000')}"
workers = int(os.getenv("WEB_CONCURRENCY", str(multiprocessing.cpu_count() * 2 + 1)))
worker_class = "uvicorn.workers.UvicornWorker"

# ── Timeouts ─────────────────────────────────────────────────────────────────
timeout = 120                # kill stuck workers (LLM worst case + margin)
graceful_timeout = 120       # drain in-flight SSE streams on SIGTERM
keepalive = 5                # seconds for HTTP keep-alive (behind nginx)

# ── Performance ──────────────────────────────────────────────────────────────
backlog = 2048               # pending connection buffer (kernel accept queue)
worker_connections = 1000    # per-worker async connection cap
max_requests = 10000         # recycle workers to bound memory fragmentation
max_requests_jitter = 1000   # avoid thundering-herd recycles

# ── Process management ───────────────────────────────────────────────────────
preload_app = True           # fork after import: faster boots, less memory
daemon = False
pidfile = "/tmp/gunicorn.pid"
user = "appuser" if os.getenv("APP_ENV") == "production" else None

# ── Logging (structlog handles JSON; gunicorn access log kept minimal) ──────
loglevel = os.getenv("LOG_LEVEL", "INFO").lower()
accesslog = "-"              # stdout -> collected by the platform
errorlog = "-"               # stderr
access_log_format = (
    '%(h)s "%(r)s" %(s)s %(b)s %(D)sus "%(a)s" [conn_reused=%({x-conn-reused}i)s]'
)

# ── Restart policy ───────────────────────────────────────────────────────────
# Liveness integration: kubelet hits /live; gunicorn heartbeats via temp files.
tmp_upload_dir = "/tmp"


def when_ready(server):
    server.log.info("Gunicorn master ready - workers spawning (production profile)")


def worker_exit(server, worker, code):
    server.log.info(f"Worker {worker.pid} exited with code {code}")
