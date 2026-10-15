# Load Testing

Encodes the capacity model from
`docs/architecture/capacity-planning.md` into executable claims.
Last reviewed: 2026-10-15.

## Profiles

| Profile | Command | Validates |
|---------|---------|-----------|
| Sustained peak | `make load-test TARGET_RPS=2000 DURATION=10m` | The 100M-MAU steady-state fleet sizing |
| Viral burst | `make load-test TARGET_RPS=10000 DURATION=5m` | HPA fast-path + cache absorption |
| Trough + zone loss | (staging only) kill an AZ at baseline | PDB + zone-spread guarantees |

## Pass Criteria (all profiles)

- Zero 5xx
- p95 < 3s, first-token p95 < 1s
- No OOMKilled pods (memory limits hold at burst)
- Cache hit-rate ≥ 30% on the repeated-question mix

## Notes

- Locust models **streaming connections** (not request-response): the
  connection-hold profile is what makes this test meaningful for chat.
- Run against staging with the production overlay shape - a load test
  against dev compose proves nothing about production.
- Results belong in the capacity doc's "Verification Cadence" table -
  update it after every run with real numbers.
