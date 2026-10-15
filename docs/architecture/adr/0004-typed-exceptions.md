# ADR-0004: Typed Exception Hierarchy with Machine-Readable Codes

- Status: Accepted
- Date: 2026-10-15
- Deciders: @AdilShamim8

## Context

The original code raised bare exceptions with prose messages. Three
downstream consumers suffered:

1. **API error envelope**: mapping exceptions to HTTP codes required
   string matching on messages - which breaks the moment wording changes.
2. **Alerting**: Prometheus rules want stable labels; "index not ready"
   as text cannot be an alert label.
3. **Retry logic**: deciding retryability (provider 5xx yes, context
   overflow no) needs structure, not `except Exception`.

## Decision

All application errors derive from `src/core/exceptions.py::ChatbotError`
carrying:

- `code` - stable, snake_case, wire-and-alert friendly
  (`llm_provider_error`, `index_not_ready`, ...)
- `http_status` - the mapped status for the API envelope
- `transient` - explicit retryability for client/circuit-breaker logic
- `details` dict - structured payload (e.g., `retry_after` for 429s)

Layers raise their specific subclass; the API translates any
untranslated `ChatbotError` to its `http_status` automatically, and
unknown exceptions become a sanitized 500 (never leak internals).

## Alternatives Considered

- **Exception-per-HTTP-status mapping table**: mapping drifts from the
  raise sites; the code lives where the error occurs instead.
- **Error-code strings returned from functions (Go-style)**: Python has
  exceptions; fighting the idiom costs more than it buys.

## Consequences

- + New errors get codes + retryability + status by construction.
- + `str(exc)` is log-friendly (`[llm_provider_error] upstream 503`).
- − Discipline required: bare `raise Exception` in a PR is a review
  reject (enforced socially; ruff rule tracking is a follow-up).
