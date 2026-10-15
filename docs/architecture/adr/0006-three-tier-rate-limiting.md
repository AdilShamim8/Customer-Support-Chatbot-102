# ADR-0006: Rate Limiting at Three Tiers

- Status: Accepted
- Date: 2026-10-15
- Deciders: @AdilShamim8

## Context

Every LLM answer costs real money and a provider quota slot. Unbounded
traffic - whether organic flash crowd, buggy client retry loops, or
deliberate abuse - converts directly into a 7-figure bill and an outage
when quota exhausts. A single rate-limit layer either blocks legitimate
burst traffic or lets abuse through.

## Decision

Rate limit at **three tiers**, each with a different clock and purpose:

| Tier | Scope | Limit | Purpose |
|------|-------|-------|---------|
| 1. Edge (nginx ingress) | per-IP | 20 r/s, burst 40, 10 conns | Absorb floods, scrapers, L7 floods before app cost |
| 2. Application (middleware) | per-API-key/client | 100 rpm (configurable) | Business fairness + quota enforcement |
| 3. Conversation (pipeline) | per-session | in-flight=1 + turn caps | Stop runaway retry loops from generating 20 parallel answers |

Redis-backed counters at tiers 2-3 (shared across pods - in-memory
limiters would multiply the effective limit by pod count, a classic
and costly bug).

Responses always include `Retry-After` and `X-RateLimit-*` headers;
429s use the typed `RateLimitExceededError` (ADR-0004).

## Alternatives Considered

- **Edge-only**: per-IP limits punish NAT'd offices/mobile carriers
  (many users, one IP); no notion of API identity.
- **App-only**: flood traffic still reaches pods and burns resources
  before being rejected.
- **Global on/off switch**: too blunt - the flash-crowd case (viral
  incident) is *legitimate* load that should be served via cache, not
  blocked globally.

## Consequences

- + Abuse economics: cost of attack > value extracted at every layer.
- + Per-tier limits are independently tunable during incidents.
- − Three knobs to reason about; documented in `.env.example` and the
  capacity doc so tuning isn't guesswork.
- − Redis dependency on the limit path: Redis down means falling back
  to per-pod in-memory limits (effective limit × pod count) - accepted
  degraded mode, alert fires (D6).
