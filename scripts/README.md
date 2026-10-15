# scripts/ Directory

Operational and development CLIs. Last updated: 2026-10-15.

| Script | Purpose | Used by |
|--------|---------|---------|
| `ingest_documents.py` | parse → chunk → embed → index the knowledge base | `make ingest` |
| `build_index.py` | rebuild indexes from processed JSONL; `--verify` gates traffic flips | index rebuild runbook |
| `evaluate_pipeline.py` | run golden sets; `--gate` enforces ADR-0007 thresholds | `make evaluate`, CI eval gate |
| `finetune_adapter.py` | LoRA/QLoRA fine-tuning with RAFT data generation | PEFT workflow |
| `preflight.sh` | post-deploy smoke: probes, metrics, golden question | deployment + rollback runbooks |
| `release.sh` | version bump with single-source verification | release process |

## Standards

- Every script: `argparse` + `--help` that actually explains usage.
- Exit codes are contracts: 0 = success, 1 = gate failure. CI and
  runbooks branch on them.
- Structured logging via `configs.logging_config.setup_logging()`.
- No script ever reads secrets from anything but the environment.
