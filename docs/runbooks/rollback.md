# Runbook: Rollback

> Owner: @AdilShamim8 · Last reviewed: 2026-10-15
>
> Rule: rollback is a *reflex*, not a debate. If a deploy is suspect and
> diagnosis will take longer than the rollback, roll back. You can always
> re-deploy once you understand what happened.

## Rollback the Application (the common case, < 5 min)

```bash
# 1. What did we deploy? (revision history is capped at 10)
kubectl -n chatbot rollout history deploy/chatbot-api

# 2. Roll back one revision
kubectl -n chatbot rollout undo deploy/chatbot-api

# 3. Watch it land (same RollingUpdate guarantees as forward deploys)
kubectl -n chatbot rollout status deploy/chatbot-api --timeout=10m

# 4. Confirm the fix with the same smoke that caught the problem
./scripts/preflight.sh https://api.ragchatbot.example.com
```

### Rolling back further than one revision

```bash
kubectl -n chatbot rollout undo deploy/chatbot-api --to-revision=3
```

### Rolling back when history was pruned (kustomize pin)

```bash
cd deploy/kubernetes
kustomize edit set image \
  ghcr.io/adilshamim8/customer-support-chatbot-102=ghcr.io/adilshamim8/customer-support-chatbot-102:sha-<LAST-KNOWN-GOOD>
kubectl apply -k .
```

## Rollback Config/Env Changes (kill-switch flips)

Env changes via `kubectl set env` are not in rollout history - undo them
the same way they were set:

```bash
kubectl -n chatbot set env deploy/chatbot-api ENABLE_RERANKING=true
kubectl -n chatbot set env deploy/chatbot-api LLM_PROVIDER=openai
```

If the source of truth (ConfigMap in git) diverged from live state,
re-apply from git *after* stabilizing: live env wins during the incident;
reconciliation happens in the postmortem follow-up.

## Rollback the Database (last resort - read first)

Order of preference:

1. **Don't.** Forward-fix with a new migration whenever possible.
2. **PITR restore** (RDS, 30-day window): restore to a point-in-time
   cluster, then dual-write/dual-read to reconcile - data written between
   restore point and incident is *lost*; quantify it before choosing.
3. **Alembic down()**: staging only. In production, `down()` on a table
   with live traffic is how a sev-2 becomes a sev-1.

## Rollback Infrastructure (Terraform)

```bash
cd deploy/terraform
terraform plan -out=rollback.tfplan    # review EVERY line
terraform apply rollback.tfplan
```

Terraform rollbacks of managed databases hit `deletion_protection` by
design - destroying data should require an explicit, deliberate unlock.

## After Any Rollback

1. Timeline entry: what was rolled back, when, from/to which revision.
2. Issue for the root cause with the deploy SHA that broke.
3. Golden-set eval case if the break was answer-quality (ADR-0007).
4. If the rollback was wrong (problem persisted), that fact goes in the
   postmortem - it constrains the real cause.
