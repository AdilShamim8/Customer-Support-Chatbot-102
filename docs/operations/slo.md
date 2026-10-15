# Service Level Objectives

> Status: Active · Owner: @AdilShamim8 · Last reviewed: 2026-10-15
>
# SLO Model

We commit to **user-perceived** outcomes, not infra health. A user does
not care that Redis is degraded; they care that the answer is wrong,
slow, or missing.

| SLO | Target | Window | Measured by |
|-----|--------|--------|-------------|
| **Availability** | 99.9% of chat requests return an answer | 30d rolling | `http_requests_total` 2xx+4xx-but-useful ÷ total (5xx + timeouts = bad) |
| **Answer latency** | p95 < 3.0s, p99 < 8.0s (full answer, streaming) | 30d | request duration histogram |
| **First token** | p95 < 1.0s (streaming endpoint) | 30d | first-token span |
| **Answer quality** | faithfulness ≥ 0.90, correctness ≥ 0.85 on golden set | weekly eval | `chatbot_eval_*` gauges |
| **Fallback rate** | < 0.5% of answers are `fallback_message` | 30d | fallback counter |

## Error Budgets (the enforcement mechanism)

99.9% over 30 days = **43 minutes 50 seconds** of full unavailability per
month. This budget is *spendable*: deploys, index rebuilds, and migrations
that cause brief blips consume it deliberately. The rules:

1. **Budget remaining > 50%**: ship freely (normal review gates).
2. **Budget 20-50%**: deploys need a stated budget-consumption estimate.
3. **Budget < 20%**: feature freezes; reliability work only.
4. **Budget exhausted**: automatic sev-2; releases freeze until 7 days
   of recovery.

The `ErrorBudgetFastBurn` alert (monitoring/alerts.yml) catches the case
where 10%+ of the monthly budget burns in an hour - i.e., an outage in
progress even if "only" 10% of requests fail.

## Why These Targets (and not "five nines")

- **99.9% not 99.99%**: chat support is not payment processing; a 0.1%
   miss costs a frustrated rephrase, not money. The extra nine would
   roughly double infra cost for invisible user benefit.
- **Quality as an SLO** is unusual but essential here: a wrong answer at
   200ms is *worse* than a correct answer at 2.5s. Faithfulness ≥ 0.90
   is the floor below which "fast wrong answers" dominate the experience.
- **Fallback rate < 0.5%**: the fallback message is the honest failure
   mode (F1) - but if it fires often, users effectively have no service
   while dashboards show green uptime. Hence its own SLO.

## SLI Implementation Notes

- Latency SLIs use the *server-side* histogram (`http_request_duration_seconds`)
  - synthetic probes measure the edge, real traffic measures the truth.
- Quality SLIs come from the weekly golden-set eval run + production
  sampled scoring (`scripts/evaluate_pipeline.py --sample 0.01`).
- 429s do NOT count against availability (they are the rate-limit
  contract working) - but a 429 *rate* above baseline alerts separately
  (it means either abuse or a capacity cliff approaching).

## Review Cadence

- Weekly: SLO dashboard review (15 min, standing meeting).
- Monthly: targets re-derived from user complaints + eval drift - are
  the numbers still the right numbers?
- Quarterly: full re-negotiation with the business (cost vs latency
  vs quality trade-offs move as models and traffic change).
