# API Quick Reference

The interactive docs (`/docs` Swagger, `/redoc`) are generated from the
same Pydantic schemas that validate requests - they are always current.
This page is the orientation layer. Last reviewed: 2026-10-15.

## Surface Map

| Endpoint | Method | Auth | Purpose |
|----------|--------|------|---------|
| `/api/v1/chat` | POST | user | Ask a question (JSON response; SSE when `"stream": true`) |
| `/api/v1/chat/{id}` | DELETE | user | End a conversation session |
| `/api/v1/chat/feedback` | POST | user | Rate an answer (drives evaluation + RAFT) |
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

Streaming is a mode of the SAME endpoint, selected per request:

```
POST /api/v1/chat
Content-Type: application/json
Accept: text/event-stream

{"message": "What is your return policy?", "stream": true}
```

Event shapes (raw text tokens, one per event):

```
data: Our 
data: return 
data: policy ...
data: [DONE]
```

First token target: p95 < 1s (SLO). A mid-stream failure emits a final
`data: [ERROR] <message>` event before the stream closes - clients must
handle `[DONE]` and `[ERROR]` shapes. The response carries
`X-Conversation-ID` so multi-turn follow-ups can continue the session.
