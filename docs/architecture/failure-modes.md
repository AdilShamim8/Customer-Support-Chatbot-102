# Failure Modes and Degraded States

> Status: Active · Owner: @AdilShamim8 · Last reviewed: 2026-10-15
>
> The question this document answers: "when X dies, what does the user
> experience, what does the system do automatically, and what do we do?"
> A production system is defined less by what it does when everything works
> than by what it does when things don't.

## Reading the Failure Table

Each row defines: **trigger → automatic behavior → user experience → action**.
"Automatic" is what the code/infra does with no human involved. If a row's
automatic behavior is "nothing", that is a bug in our resilience design.

## Tier 1: Total Failures

| # | Failure | Automatic behavior | User experience | Action / runbook |
|---|---------|--------------------|-----------------| ---------------|
| F1 | **LLM provider outage** (5xx/timeout across provider) | Circuit breaker opens after 5 failures; requests served `fallback_message` (a sincere "systems are down" + human handoff), never a hang | Polite refusal, instant | [incident-response#llm](../runbooks/incident-response.md#llm-provider-outage); switch provider via `LLM_PROVIDER` |
| F2 | **Redis loss** (conversation memory) | CacheUnavailableError caught; service continues **stateless** - follow-up turns lose prior context | First turn works; follow-ups need full questions | Accept degraded; restore Redis; sessions self-heal on TTL expiry |
| F3 | **Postgres loss** | Feedback/evaluation writes buffer to log; chat serving unaffected (reads are not on the hot path) | Invisible to users | Restore HA failover; replay buffered writes |
| F4 | **Vector index down / empty** | Readiness flips false → pod leaves Service; if fleet-wide, `/ready` fails while `/live` stays green (serving tier healthy, dependency not) | 503s from LB, not hangs | [vector-index-rebuild](../runbooks/vector-index-rebuild.md) |
| F5 | **Elasticsearch down** (keyword half of hybrid) | Hybrid falls back to vector-only retrieval; recall dip, precision mostly held | Slightly worse answers, no errors | Rebuild ES; monitor `retrieval_recall` metric |
| F6 | **Zone loss** (whole AZ) | Zone-spread keeps ≥ 2/3 pods; PDB blocks unsafe eviction; HPA replaces lost capacity in ~60-90s | Brief latency bump | Nothing (by design) - verify via `kubectl get pods -o wide` spread |

## Tier 2: Degradations (the dangerous ones - no error, just worse)

| # | Failure | Symptom (metric) | Automatic behavior | Action |
|---|---------|------------------|--------------------|--------|
| D1 | **Silent cache miss regression** (semantic cache broken) | `cache_hit_rate` < 5% while traffic mix unchanged; LLM cost 2x | None (cost, not latency) | Check Redis latency; verify threshold drift after embedding model change |
| D2 | **Index staleness** (docs updated, chunks not re-ingested) | Context-relevance scores drift down over days; complaint keywords in feedback ("outdated") | Nightly eval canary on golden questions | Re-run ingestion pipeline; see [vector-index-rebuild](../runbooks/vector-index-rebuild.md) |
| D3 | **Reranker model drift** (provider silently changes model) | Answer correctness dips; latency shape changes | Kill-switch `ENABLE_RERANKING` available | Diff eval report vs last release; pin model version |
| D4 | **Prompt regression** (a "small copy tweak") | Faithfulness/correctness drop on golden set | Eval gate in CI blocks merge if wired | Revert; require eval diff in PR template |
| D5 | **Token-limit creep** (knowledge docs grow; context overflows) | 413s or truncated citations; `context_length_exceeded` error code | Context assembler already truncates by token budget | Re-chunk with smaller `CHUNK_SIZE`; prune stale docs |
| D6 | **Conversation memory leak** (Redis full, LRU thrash) | Redis eviction storm; users report amnesia mid-chat | `maxmemory-policy allkeys-lru` sheds history first | Raise memory or shorten TTL; alert already fires on saturation |

## Tier 3: Self-Inflicted Failures (the most common kind)

| # | Failure | Root cause | Prevention (in repo today) |
|---|---------|-----------| ---------------------------|
| S1 | **Bad deploy** | Untested prompt/config change | CI quality gates + eval diff + rolling deploy with maxUnavailable=0 |
| S2 | **Secret leak** | .env committed | `.gitignore` + gitleaks pre-commit + CI secret scan (3 layers) |
| S3 | **Migrations on live DB** | Schema drift | Alembic with review-required CODEOWNERS on `migrations/` |
| S4 | **Runaway HPA cost** | Metric misconfiguration (avgValue typo) | HPA ceiling + budget alerts; runbook documents the math |
| S5 | **Stale dependency CVE** | Ignored updates | Dependabot weekly + pip-audit CI + Trivy container scan |

## The Degradation Ladder (design intent)

When multiple things fail simultaneously, the system walks *down* this ladder
deliberately rather than erroring out:

```
Full quality     hybrid retrieval + rerank + citations + memory + cache
  ↓ ES down      vector-only retrieval (recall dip)
  ↓ rerank off   retrieval order, no cross-encoder (precision dip)
  ↓ memory off   single-turn answers (follow-ups degrade)
  ↓ cache off    every answer is a live LLM call (cost, latency 2x)
  ↓ LLM down     fallback_message + human handoff (refusal, not hang)
```

Every step is a flag in `configs/settings.py`; the ladder is also the incident
*recovery* order in reverse: restore memory before cache before rerank, because
each step restores more user-visible quality per unit of engineering effort.

## Known Fragilities (honest inventory)

1. **Single-provider LLM dependency** - mitigated, not eliminated. Multi-live-
   provider routing is designed (LLMClientFactory) but the fallback message
   path is the tested behavior today.
2. **Reranker is in-process CPU** - convenient and fast, but a pathological
   batch can steal CPU from the event loop. Mitigation: HPA reacts to exactly
   this; kill-switch exists.
3. **Conversation state TTL is 1h** - users returning after 61 minutes lose
   context. A durable Postgres-backed session layer is sketched but not wired.
4. **Eval golden set is small** - the CI eval gate is as strong as the golden
   question set; growing it is a standing TODO tracked in issues.
