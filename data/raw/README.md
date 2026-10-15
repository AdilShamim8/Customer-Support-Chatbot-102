# Raw Documents

The **source of truth** for the knowledge base. Everything downstream
(processing, chunking, indexing) is a rebuildable projection of what
lives here. Last updated: 2026-10-15.

## What Belongs Here

- Original support documents: PDFs, DOCX, HTML exports, Markdown, TXT
- Policy documents with clear ownership (doc IDs like POL-RET-001)
- Version-dated content (the freshness contract - see below)

## What Never Belongs Here

- Secrets or credentials of any kind
- Internal-only HR/legal documents (retrieval reaches production prompts)
- Unversioned drafts - ingested garbage answers garbage

## The Freshness Contract

Every document should carry an effective date in its header (see
`sample_docs/*.md` for the pattern). Answers cite these dates; stale
docs produce answers like "per the 2024 policy..." - the context-
relevance drift alert (D2) exists to catch exactly this rot.

## After Adding Documents

```bash
make ingest                # parse -> chunk -> embed -> index both halves
python scripts/build_index.py --verify   # gates before traffic flip
```

See `docs/runbooks/vector-index-rebuild.md` for the blue/green flow.
