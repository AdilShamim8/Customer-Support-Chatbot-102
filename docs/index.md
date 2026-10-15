# Customer Support Chatbot — Engineering Documentation

Production-grade RAG answer service: hybrid retrieval, prompt engineering,
evaluation gates, and the operational scaffolding to serve it at scale.
Last updated: 2026-10-15 · Build locally: `mkdocs serve`

| Start here | |
|---|---|
| 🏗️ How it works | [System Overview](architecture/system-overview.md) |
| ⏱️ Where the milliseconds go | [Request Data Flow](architecture/data-flow.md) |
| 📈 How it scales to 100M+ | [Scaling Design](architecture/scaling-100m-users.md) |
| 💥 How it fails (and degrades) | [Failure Modes](architecture/failure-modes.md) |
| 🧮 Why every infra number | [Capacity Planning](architecture/capacity-planning.md) |
| 🧠 How prompts are engineered | [Prompting Playbook](prompting/playbook.md) |
| 📏 How quality is measured | [Evaluation Metrics](evaluation/metrics.md) |
| 🚨 How incidents are handled | [Runbooks](runbooks/README.md) |
| 📟 What on-call means | [On-Call Guide](operations/on-call.md) |
| 🎯 What we promise users | [SLOs](operations/slo.md) |
| 🔐 What the attackers see | [Threat Model](security/threat-model.md) |
| 🧑‍💻 First contribution | [Getting Started](development/getting-started.md) |
| ✅ How reviews happen | [Code Review Checklist](development/code-review-checklist.md) |
| 🔧 Something is broken | [Troubleshooting](development/troubleshooting.md) |

## Architecture — how it is built

Seven ADRs record the decisions behind hybrid retrieval, reranking,
typed errors, SSE streaming, three-tier rate limiting, and eval gates -
each with the alternatives genuinely considered:
[ADR index](architecture/adr/0001-record-architecture-decisions.md).

## Operations — how it runs

The service commits to user-perceived SLOs (99.9% availability, p95
latency, faithfulness ≥ 0.90) with error budgets that gate release
speed. Alerting fires on symptoms; every alert links a runbook.

## Documentation Principles

1. **Numbers over adjectives** - capacity docs derive, they don't gesture.
2. **Every alert links a runbook** - a page without a procedure is a prank.
3. **ADRs record why** - the review that approved a decision is not a
   durable explanation of it.
4. **Dates matter** - every page carries a "last reviewed" stamp; stale
   docs are labeled stale, not silently wrong.

## Repository Map

```
docs/
├── architecture/     overview, data flow, scaling, failure modes,
│   └── adr/           capacity, 7 ADRs
├── operations/       SLOs, monitoring guide
├── runbooks/         incident, deploy, rollback, index rebuild
├── prompting/        strategy playbook
├── evaluation/       metrics reference
├── development/      getting started, troubleshooting
├── api/              surface map and conventions
└── security/         threat model
```
