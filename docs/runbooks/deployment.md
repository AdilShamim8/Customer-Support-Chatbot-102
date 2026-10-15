# Runbook: Deployment

> Owner: @AdilShamim8 · Last reviewed: 2026-10-15

## What a Deploy Looks Like

The pipeline (`.github/workflows/docker.yml` + `release.yml`) builds,
scans, and publishes an image per git SHA. Deploying = updating the
Kustomize image tag and letting the RollingUpdate (maxUnavailable=0,
maxSurge=25%) replace pods gradually.

## Standard Deploy

```bash
# 1. Verify the version you intend is green upstream
gh run list --workflow ci.yml --branch main --limit 1   # must be green

# 2. Pin the new image tag
cd deploy/kubernetes
kustomize edit set image \
  ghcr.io/adilshamim8/customer-support-chatbot-102=ghcr.io/adilshamim8/customer-support-chatbot-102:sha-<SHA>

# 3. Apply
kubectl apply -k .
kubectl -n chatbot rollout status deploy/chatbot-api --timeout=10m

# 4. Smoke the golden questions against production
./scripts/preflight.sh https://api.ragchatbot.example.com
```

## Safety Properties (already wired - know why they exist)

| Property | Where | What it buys |
|----------|-------|--------------|
| maxUnavailable=0 | deployment.yaml | Old pods only die after new ones answer |
| Readiness gating | /ready | A bad new version never receives traffic |
| terminationGrace 130s | deployment.yaml | In-flight SSE answers drain, not drop |
| startupProbe 150s | deployment.yaml | Cold-boot index warm-up doesn't crash-loop |
| HPA floor 6 | hpa.yaml | Deploy during trough still serves baseline |
| Trivy scan | docker.yml | Known-CRITICAL images don't deploy |

## Canary Shape (manual, for risky changes)

For retrieval/prompt/model changes with eval implications:

1. Deploy to staging; run `scripts/evaluate_pipeline.py` - compare the
   three metrics to the last production baseline.
2. Scale canary: `kubectl -n chatbot scale deploy/chatbot-canary --replicas=2`
   (a labeled copy of the Deployment with the new tag + the same Service
   selector minus anti-affinity weight) - route ~5% by having 2 canary
   pods against 40 prod pods (pod-count proportionality).
3. Watch `chatbot_eval_*`, error rate, and first-token latency for 30 min.
4. Promote by pinning the main Deployment to the new tag; delete canary.

## Migration Deploys (schema changes)

1. Migrations run as a **pre-deploy Job**, never at pod boot: Alembic
   forward-only in prod (`migrations/` is CODEOWNERS-gated).
2. Expand-contract: add nullable columns → deploy code that writes both →
   backfill batch job → deploy code reading new → drop old column next
   release. Never a breaking migration in one step.
3. Rollback of a migration is the *next* migration, not `down()` on prod.

## Deploy Freezes

- During a sev-1 incident: no deploys except kill-switch env flips.
- Freeze windows: peak-traffic hours (see capacity doc's diurnal model) -
  deploy at trough, never at peak.
