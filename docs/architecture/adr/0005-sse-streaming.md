# ADR-0005: SSE Streaming for Chat Responses

- Status: Accepted
- Date: 2026-10-15
- Deciders: @AdilShamim8

## Context

A complete support answer takes 2-15s to generate. Waiting silently for
the full answer feels broken to users - measured UX research consistently
shows perceived latency drops ~50% when the first token appears within
~1s and text streams thereafter.

Transport options evaluated: WebSockets, long-polling, and
Server-Sent Events (SSE).

## Decision

Stream answers over **SSE** (`text/event-stream`) on
`/api/v1/chat/stream`:

- Unidirectional (client sends one request, server streams tokens) -
  matches the actual data flow; no client→server channel needed.
- Works over plain HTTP/1.1 and HTTP/2 - no upgrade dance, trivially
  compatible with existing nginx/K8s ingress (with buffering off and
  long read timeouts - both wired in `deploy/nginx/nginx.conf` and the
  ingress annotations).
- Automatic reconnection protocol built into the browser EventSource.
- Non-streaming JSON endpoint retained for API clients and tests.

## Alternatives Considered

- **WebSockets**: bidirectional power we don't use; breaks with many
  proxies/LBs without extra config; connection-per-pod complicates the
  stateless scaling model.
- **Chunked JSON polling**: more client complexity, worse latency floor.
- **Non-streaming only**: simplest, but the perceived-latency cost is
  user-visible and permanent.

## Consequences

- + Perceived latency ~halved; first-token timeout is an explicit SLO
  (`STREAM_FIRST_TOKEN_TIMEOUT_SECONDS=10`).
- − Infra must be SSE-aware: proxy buffering OFF, read timeouts ≥ 120s,
  connection counts sized for streams held open (capacity doc §2).
- − Per-token backpressure: a slow client holds a worker stream; the
  first-token timeout bounds the worst case.
- − Load tests must model streaming connections (locustfile does).
