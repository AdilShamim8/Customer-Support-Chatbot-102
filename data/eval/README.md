# Evaluation Data

Golden sets power the release-quality gate (ADR-0007) and the weekly
drift canary. Last updated: 2026-10-15.

## The Golden Sets

| File | Cases | Purpose |
|------|-------|---------|
| `golden_faq.jsonl` | 10 | Single-document factual questions - the baseline floor |
| `golden_multihop.jsonl` | 7 | Cross-document reasoning ("bought X months ago + symptom Y → which policy?") |
| `golden_adversarial.jsonl` | 10 | Prompt injection, unanswerable, ambiguous, phishing attempts - the safety floor |

## Record Schema

```json
{
  "question_id": "faq-001",
  "category": "faq | multi_hop | adversarial | unanswerable | ambiguous",
  "question": "…",
  "expected_answer": "…",
  "expected_sources": ["returns_policy.md"],
  "answerable": true
}
```

`answerable: false` cases measure the REFUSAL contract: the correct
behavior is declining gracefully and offering real support topics -
never a confident fabrication.

## Composition Targets (keep roughly balanced)

- ~60% FAQ-shape · ~20% multi-hop · ~10% adversarial · ~10% ambiguous
- Every production incident contributes a case (postmortem rule).
- Cases are versioned like code: dataset changes get reviewed.

## Running

```bash
make evaluate      # full suite → data/eval/report.json
make eval-gate     # CI mode: FAQ set + threshold check
```

## Reports (git-ignored)

`report.json`, `ci_report.json`, `gate_report.json` are run artifacts -
never commit them. The metric definitions live in
[docs/evaluation/metrics.md](../../docs/evaluation/metrics.md).
