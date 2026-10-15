# Sample Customer Support Documents

A realistic mini-corpus for development, demos, and the golden-set
evaluation. Last updated: 2026-10-15.

## The Corpus

| Document | Doc ID | Covers |
|----------|--------|--------|
| `faq.md` | FAQ-001 | General questions - the original sample doc |
| `returns_policy.md` | POL-RET-001 | Return windows, restocking fees, DOA handling |
| `shipping_guide.md` | POL-SHP-002 | Carriers, delays, customs, address changes |
| `account_security.md` | POL-ACC-003 | Sign-in, 2FA, data export, phishing |
| `warranty_terms.md` | POL-WAR-004 | Coverage matrix, claims, AcmeCare+, voids |

The documents deliberately **overlap** (a warranty question may need
the returns policy too) - that cross-referencing is what the multi-hop
golden set (`data/eval/golden_multihop.jsonl`) exercises.

## Supported Formats
- `.pdf` - Product manuals, policy documents
- `.docx` - Word documents
- `.html` - Help center articles
- `.md` - Markdown documentation
- `.txt` - Plain text FAQs

## Ingesting Documents

```bash
python scripts/ingest_documents.py \
    --source-dir ./data/sample_docs \
    --chunk-strategy hierarchical \
    --parse-strategy rule_based
```

Or simply: `make ingest`. Verify before serving:
`python scripts/build_index.py --verify`.
