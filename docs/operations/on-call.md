# On-Call Guide

What it actually means to carry the pager for this service.
Last reviewed: 2026-10-15. Procedures: [incident-response.md](../runbooks/incident-response.md).

## The Pager Contract

You will be paged for (and only for) user-visible symptoms:

- Error rate above 2% for 5 minutes (or fast-burn: 10% in an hour)
- p95 latency above 3s for 10 minutes
- Crash-looping pods
- LLM provider or vector index down

You will NOT be paged for CPU, disk, or anything a user cannot feel.
If a cause-only alert fires without symptom alerts, it is a warning -
handle it in business hours.

## The First Five Minutes (memorize this)

1. Acknowledge the page.
2. Snapshot: `kubectl -n chatbot get pods,deploy,hpa -o wide` + Grafana
   screenshot.
3. Declare severity (over-communicate; downgrade later).
4. Mitigate with a kill-switch BEFORE diagnosing (the ladder:
   rerank off → cache off → provider switch → edge shed).
5. Start the timestamped timeline.

## What You Are Authorized to Do Alone

- Flip any kill-switch env var (they exist to be flipped)
- Roll back one deployment revision
- Scale the HPA floor up
- Shed edge rate limits during a viral wave

## What Requires a Second Pair of Eyes

- Database restores / PITR (data-loss decisions)
- Anything touching `migrations/` under load
- Multi-region failover

## Post-Incident (within 48h)

- Blameless postmortem from the timeline.
- Every action item becomes an issue with an owner and date.
- The incident's signature question joins the golden eval set.

## The Honest Notes Section

- The LLM provider is the dependency most likely to page you - the
  fallback message path is tested precisely for this.
- The degraded modes are designed to be BORING: redis loss means
  slightly worse conversations, not sirens.
- If you are paged twice for the same root cause, the second page is a
  process bug - file it like code.
