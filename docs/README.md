# Documentation Index

Single entry point for everything written about this system.
Last updated: 2026-10-15 · Build: `mkdocs serve` · Site nav: `mkdocs.yml`

## Architecture — how it is built

| Doc | One-liner |
|-----|-----------|
| [system-overview.md](architecture/system-overview.md) | Components, four-stage pipeline, design principles |
| [data-flow.md](architecture/data-flow.md) | One request, millisecond by millisecond, failure branches |
| [scaling-100m-users.md](architecture/scaling-100m-users.md) | The 100M-200M MAU design: bottlenecks and mitigations |
| [capacity-planning.md](architecture/capacity-planning.md) | Little's Law derivations behind every infra number |
| [failure-modes.md](architecture/failure-modes.md) | Failure catalog + the degradation ladder |
| [ADR index](architecture/adr/0001-record-architecture-decisions.md) | Seven decisions with alternatives and consequences |

## Operations — how it runs

| Doc | One-liner |
|-----|-----------|
| [slo.md](operations/slo.md) | Targets, error budgets, enforcement rules |
| [monitoring.md](operations/monitoring.md) | Instrumentation map, golden dashboards, cardinality discipline |
| [runbooks/](runbooks/README.md) | Incident, deploy, rollback, index rebuild |

## Engineering — how to change it

| Doc | One-liner |
|-----|-----------|
| [prompting/playbook.md](prompting/playbook.md) | Four strategies, assembly order, anti-patterns |
| [evaluation/metrics.md](evaluation/metrics.md) | The three metrics + diagnostic matrix |
| [development/getting-started.md](development/getting-started.md) | 10-minute setup |
| [development/troubleshooting.md](development/troubleshooting.md) | Symptom → cause → fix |
| [api/README.md](api/README.md) | Surface map, conventions, SSE contract |

## Security — how it's attacked

| Doc | One-liner |
|-----|-----------|
| [security/threat-model.md](security/threat-model.md) | STRIDE per component, prompt-injection mitigations |

## Writing Rules

1. Numbers over adjectives. 2. Every alert links a runbook. 3. ADRs
record why. 4. "Last reviewed" stamps on every page - stale docs are
labeled stale, not silently wrong.
