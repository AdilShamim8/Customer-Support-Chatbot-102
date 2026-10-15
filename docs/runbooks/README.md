# Runbooks

Operational procedures - written to be executable at 3am without
context. Every alert in `monitoring/alerts.yml` links to one of these.
Last reviewed: 2026-10-15.

| Runbook | When it fires |
|---------|--------------|
| [incident-response.md](incident-response.md) | Any page: error rate, latency, crash loops, provider outages |
| [deployment.md](deployment.md) | Planned deploys, canaries, migrations |
| [rollback.md](rollback.md) | Bad deploys, bad config flips, worst-case DB recovery |
| [vector-index-rebuild.md](vector-index-rebuild.md) | Index down/stale/corrupt; embedding model changes |

## Writing Standard

1. **Commands are copy-pasteable** - real kubectl/curl lines, not prose.
2. **Order is by speed**: mitigate first, diagnose second.
3. **Every procedure states how to verify it worked** - a step without
   a verification is a hope, not a procedure.
4. **Timestamp the review date** - stale runbooks are worse than none.

## The Kill-Switch Ladder (fastest mitigations)

```bash
kubectl -n chatbot set env deploy/chatbot-api ENABLE_RERANKING=false
kubectl -n chatbot set env deploy/chatbot-api SEMANTIC_CACHE_ENABLED=false
kubectl -n chatbot set env deploy/chatbot-api LLM_PROVIDER=anthropic
```

All env flips roll out with zero downtime (readiness-gated). Full
reasoning: [incident-response.md](incident-response.md).
