# Deployment Stack

Everything needed to run this service for real. Last updated: 2026-10-15.

| Path | What | When you touch it |
|------|------|-------------------|
| `kubernetes/` | Base manifests: Deployment, HPA, PDB, Ingress, NetworkPolicy, ConfigMap, Redis, Postgres, ServiceMonitor, PriorityClass | Serving-tier topology changes |
| `kubernetes/overlays/staging/` | Kustomize overlay: 2 replicas, relaxed rollout | Pre-production verification |
| `kubernetes/overlays/production/` | Kustomize overlay: strict availability strategy | Production deploys |
| `terraform/` | VPC (3 AZ), EKS, ElastiCache (multi-AZ), RDS (HA + PITR), Secrets Manager | Platform provisioning / capacity |
| `nginx/` | Edge config: SSE-safe proxying, rate limits, JSON logs | Edge behavior changes |

## Reading Order (first time)

1. `../docs/architecture/scaling-100m-users.md` - the design these manifests encode
2. `../docs/architecture/capacity-planning.md` - where every number comes from
3. `kubernetes/deployment.yaml` comments - they explain *why*, not just what
4. `../docs/runbooks/deployment.md` - the operating procedure

## Defaults You Should Not Quietly Change

- `maxUnavailable: 0` (production) - availability beats iteration speed
- `terminationGracePeriodSeconds: 130` - must exceed gunicorn's 120s drain
- HPA floor 6 - zone-loss survivability at baseline traffic
- `deletion_protection` on RDS - intentional friction against data loss

## Deploy

```bash
kubectl apply -k kubernetes/overlays/production
kubectl -n chatbot rollout status deploy/chatbot-api
../../scripts/preflight.sh https://api.yourdomain.com $KEY
```
