# Data Directory Map

Everything the system knows lives under here. Last updated: 2026-10-15.

```
data/
├── raw/           SOURCE OF TRUTH - original documents, version-dated
├── processed/     Derived: chunked JSONL (never hand-edited)
├── sample_docs/   The demo corpus (FAQ + 4 policy docs, cross-linked)
└── eval/          Golden sets + reports (reports git-ignored)
```

## The Golden Rule

`raw/` is truth; everything else is a projection that can be rebuilt:
`make ingest` → processed → indexes. When retrieval misbehaves, compare
against raw - never debug the derived layer by editing it.

## Lifecycle

| Directory | Written by | Deleted by | Backup posture |
|-----------|-----------|------------|----------------|
| `raw/` | humans, review-gated | never casually | versioned in git |
| `processed/` | ingestion pipeline | freely rebuildable | not backed up |
| `sample_docs/` | repo maintainers | never | versioned in git |
| `eval/` golden sets | review-gated (like code) | never | versioned in git |
| `eval/` reports | evaluation runs | anytime | not backed up |
