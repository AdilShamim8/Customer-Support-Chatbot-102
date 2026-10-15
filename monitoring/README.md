# Monitoring Stack

The observability layer answers three questions (see
`../docs/operations/monitoring.md`): is it healthy, why is this request
slow, and is quality drifting? Last updated: 2026-10-15.

| File | Role |
|------|------|
| `prometheus.yml` | Scrape config (targets, intervals) |
| `alerts.yml` | The alert catalog - every rule links a runbook |
| `otel-collector.yaml` | Tail-based trace sampling (errors always kept) |
| `grafana/dashboards/chatbot_dashboard.json` | Golden operational dashboard |
| `grafana/dashboards/rag_quality_dashboard.json` | Answer-quality SLO dashboard |
| `grafana/dashboards/provisioning.yml` | Grafana auto-provisioning |

## Alert Philosophy

Alerts fire on **symptoms users feel** (error rate, latency, fallbacks),
never on causes alone (CPU high). Every alert's annotation carries the
runbook URL - a page without a procedure is a prank.

## Local Stack

```bash
docker-compose up -d prometheus grafana
# Grafana: http://localhost:3001 (admin/admin) - dashboards auto-load
```

## Cardinality Rules (protect the monitor itself)

- Label by bounded sets only: `status`, `provider`, `strategy`
- Never: user IDs, conversation IDs, prompt text
- Synthetic probes measure the edge; real traffic measures the truth
