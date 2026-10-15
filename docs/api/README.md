# API Quick Reference

The interactive docs (`/docs` Swagger, `/redoc`) are generated from the
same Pydantic schemas that validate requests - they are always current.
This page is the orientation layer. Last reviewed: 2026-10-15.

## Surface Map

| Endpoint | Method | Auth | Purpose |
|----------|--------|------|---------|
| `/api/v1/chat` | POST | user | Ask a question (JSON response) |
| `/api/v1/chat/stream` | POST | user | Ask a question (SSE token stream) |
| `/api/v1/chat/{id}` | DELETE | user | End a conversation session |
| `/api/v1/feedback` | POST | user | Rate an answer (drives evaluation + RAFT) |
| `/api/v1/admin/documents/upload` | POST | admin | Ingest a document |
| `/api/v1/admin/evaluate` | POST | admin | Trigger evaluation run |
| `/api/v1/admin/stats` | GET | admin | Pipeline + usage statistics |
| `/health` | GET | none | Component-level health (humans/dashboards) |
| `/ready` | GET | none | Kubernetes readiness probe |
| `/live` | GET | none | Kubernetes liveness probe |
| `/metrics` | GET | none | Prometheus scrape target |

## Conventions

- **Auth**: `X-API-Key` header or `Authorization: Bearer` token
  (both accepted; keys identify the account, not the IP).
- **Errors**: uniform envelope `{code, message, transient, details}`
  from the typed hierarchy (ADR-0004) - `code` is stable for alerting,
  `transient` tells retry logic what to do.
- **429s** always carry `Retry-After` + `X-RateLimit-*` headers.
- **Correlation**: every response carries `X-Request-ID`; include it in
  bug reports.
- **Versioning**: `/api/v1/` prefix - breaking changes add `/v2/`, they
  never mutate v1.

## Streaming Contract (SSE)

```
POST /api/v1/chat/stream
Accept: text/event-stream

data: {"token": "Our "}
data: {"token": "return "}
...
data: [DONE]
```

First token target: p95 < 1s (SLO). Errors mid-stream arrive as a final
`data: {"error": {...}}` event before the stream closes - clients must
handle both shapes.
