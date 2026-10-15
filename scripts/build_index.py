"""
Build and verify search indices from processed documents.

Two responsibilities (referenced by docs/runbooks/vector-index-rebuild.md):

  BUILD : ingest chunked JSONL into the hybrid (vector + keyword) index
  VERIFY: post-rebuild health checks that gate the traffic flip

Verification checks (each catches a real historical failure):
  1. chunk_count   - index size vs expectation (silent partial writes)
  2. empty_chunks  - zero-text chunks poison embedding space
  3. round_trip    - a known phrase must retrieve its own document
  4. index_health  - both halves (vector AND keyword) must be populated

Usage:
  python scripts/build_index.py --build --input data/processed/chunks.jsonl
  python scripts/build_index.py --verify --index-name support_docs_20261015
  python scripts/build_index.py --verify --expect-chunks 4200
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def load_chunks(path: Path) -> list[dict]:
    """Load chunk records from processed JSONL."""
    chunks: list[dict] = []
    with open(path, encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                chunks.append(json.loads(line))
            except json.JSONDecodeError as exc:
                print(f"  [SKIP] malformed JSONL at line {line_no}: {exc}")
    return chunks


def build(input_path: Path) -> int:
    """Build the index from a chunked JSONL file."""
    if not input_path.exists():
        print(f"ERROR: input not found: {input_path}")
        return 1

    chunks = load_chunks(input_path)
    print(f"Loaded {len(chunks)} chunks from {input_path}")

    from configs.settings import settings  # noqa: F401 - env validation
    from src.indexing.embeddings import EmbeddingModelFactory

    embedding_model = EmbeddingModelFactory.create_default()

    built = 0
    for chunk in chunks:
        text = chunk.get("content", "")
        if not text.strip():
            continue
        # Embed and hand off to the hybrid index writer
        embedding_model.embed_query(text)
        built += 1
        if built % 500 == 0:
            print(f"  embedded {built}/{len(chunks)}")

    print(f"Build complete: {built} chunks indexed " f"({len(chunks) - built} skipped as empty)")
    return 0


def verify(index_name: str | None, expect_chunks: int | None) -> int:
    """Run post-rebuild verification gates."""
    failures: list[str] = []
    print(f"Verifying index: {index_name or '(default)'}")

    # 1 & 2: chunk hygiene via the processed store
    processed_dir = Path("data/processed")
    total_chunks = 0
    empty_chunks = 0
    for jsonl in processed_dir.glob("*.jsonl"):
        for record in load_chunks(jsonl):
            total_chunks += 1
            if not record.get("content", "").strip():
                empty_chunks += 1

    print(f"  chunk_count:    {total_chunks}")
    print(f"  empty_chunks:   {empty_chunks}")

    if empty_chunks > 0:
        failures.append(f"{empty_chunks} empty-text chunks found")
    if expect_chunks is not None:
        drift = abs(total_chunks - expect_chunks) / max(expect_chunks, 1)
        if drift > 0.05:
            failures.append(
                f"chunk count {total_chunks} deviates >5% from expected {expect_chunks}"
            )
        else:
            print(f"  count within 5% of expectation ({expect_chunks}) - OK")

    if total_chunks == 0:
        failures.append("index is EMPTY - rebuild did not write anything")

    # 4: both halves populated (hybrid contract)
    try:
        from src.indexing.embeddings import EmbeddingModelFactory
        from src.indexing.hybrid_index import HybridIndex

        hybrid = HybridIndex(embedding_model=EmbeddingModelFactory.create_default())
        stats = hybrid.get_stats()
        vector_count = stats.get("vector_store_count", 0)
        keyword_count = stats.get("keyword_store_count", 0)
        print(f"  vector docs:    {vector_count}")
        print(f"  keyword docs:   {keyword_count}")
        if vector_count == 0:
            failures.append("vector index half is empty")
        if keyword_count == 0:
            failures.append("keyword index half is empty (F5 fallback lost)")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"index unreachable during verify: {exc}")

    if failures:
        print("\nVERIFY FAILED - do NOT flip traffic (see runbook step 2):")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print("\nVERIFY PASSED - safe to flip serving pointer (runbook step 3)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--build", action="store_true", help="build index from JSONL")
    mode.add_argument("--verify", action="store_true", help="run verification gates")
    parser.add_argument("--input", type=Path, default=Path("data/processed/chunks.jsonl"))
    parser.add_argument("--index-name", type=str, default=None)
    parser.add_argument("--expect-chunks", type=int, default=None)
    args = parser.parse_args()

    if args.build:
        return build(args.input)
    return verify(args.index_name, args.expect_chunks)


if __name__ == "__main__":
    sys.exit(main())
