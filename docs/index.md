# Customer Support Chatbot — Engineering Documentation

Production-grade RAG answer service: hybrid retrieval, prompt engineering,
evaluation gates, and the operational scaffolding to serve it at scale.

| Start here | |
|---|---|
| 🏗️ How it works | [System Overview](architecture/system-overview.md) |
| 📈 How it scales to 100M+ | [Scaling Design](architecture/scaling-100m-users.md) |
| 💥 How it fails (and degrades) | [Failure Modes](architecture/failure-modes.md) |
| 🧠 How prompts are engineered | [Prompting Playbook](prompting/playbook.md) |
| 📏 How quality is measured | [Evaluation Metrics](evaluation/metrics.md) |
| 🚨 How incidents are handled | [Runbooks](runbooks/incident-response.md) |
| 🔐 What the attackers see | [Threat Model](security/threat-model.md) |
| 🧑‍💻 First contribution | [Getting Started](development/getting-started.md) |

## Documentation Principles

1. **Numbers over adjectives** - capacity docs derive, they don't gesture.
2. **Every alert links a runbook** - a page without a procedure is a prank.
3. **ADRs record why** - the code review that approved a decision is not
   a durable explanation of it.
4. **Dates matter** - documents carry "last reviewed" stamps; stale docs
   are labeled stale, not silently wrong.

## Repository Map

```
docs/
├── architecture/     scaling, failure modes, capacity, ADRs
├── operations/       SLOs, monitoring guide
├── runbooks/         incident, deploy, rollback, index rebuild
├── prompting/        strategy playbook
├── evaluation/       metrics reference
├── development/      getting started
└── security/         threat model
```

Build the site locally: `pip install mkdocs-material && mkdocs serve`
