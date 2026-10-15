# Sample Customer Support Documents

Place your support documentation here for ingestion.

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