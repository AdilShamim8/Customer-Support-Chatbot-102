# Kustomize Overlays

Environment-specific patches on the shared base. Last reviewed: 2026-10-15.

| Overlay | Shape | Philosophy |
|---------|-------|------------|
| `staging/` | 2 replicas, HPA 2-20, maxUnavailable=1, PDB=1 | Iteration speed; can sacrifice availability |
| `production/` | base fleet, maxUnavailable=0, maxSurge=50% | Availability beats speed, always |

## Usage

```bash
kubectl apply -k deploy/kubernetes/overlays/staging
kubectl apply -k deploy/kubernetes/overlays/production
```

## Rules

1. The BASE carries production-grade defaults - overlays only *deviate
   deliberately*, they never relax silently.
2. Every deviation needs its reason in a comment in the overlay.
3. Staging mirrors production's *shape* (same resources, same probes,
   same config surface) - different numbers, never different topology.
   A staging environment that doesn't resemble production tests nothing
   about production.
