#!/usr/bin/env python3
"""
Document ingestion pipeline.
Orchestrates: Parse → Chunk → Index

Usage:
    python scripts/ingest_documents.py --source-dir ./data/raw --strategy hierarchical
    python scripts/ingest_documents.py --source-dir ./data/raw --parse-strategy ai_based
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import structlog
from tqdm import tqdm

from configs.logging_config import setup_logging
from configs.settings import settings
from src.parsing.document_parser import DocumentParserFactory, ParseStrategy
from src.parsing.chunking import ChunkingStrategy, ChunkerFactory
from src.indexing.hybrid_index import HybridIndex
from src.indexing.embeddings import EmbeddingModelFactory, EmbeddingProvider

logger = structlog.get_logger(__name__)

SUPPORTED_EXTENSIONS = {".pdf", ".html", ".htm", ".docx", ".md", ".txt"}


def ingest_documents(
    source_dir: Path,
    parse_strategy: ParseStrategy = ParseStrategy.RULE_BASED,
    chunk_strategy: ChunkingStrategy = ChunkingStrategy.HIERARCHICAL,
    chunk_size: int = settings.chunk_size,
    chunk_overlap: int = settings.chunk_overlap,
    dry_run: bool = False,
) -> dict:
    """
    Full ingestion pipeline: Parse → Chunk → Embed → Index.
    
    Returns:
        Summary statistics dict
    """
    stats = {
        "files_found": 0,
        "files_parsed": 0,
        "files_failed": 0,
        "total_chunks": 0,
        "indexed_chunks": 0,
    }
    
    # Collect all supported files
    source_path = Path(source_dir)
    if not source_path.exists():
        raise FileNotFoundError(f"Source directory not found: {source_dir}")
    
    files = [
        f for f in source_path.rglob("*")
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
    ]
    
    stats["files_found"] = len(files)
    logger.info(
        "Starting ingestion",
        source_dir=str(source_dir),
        files_found=len(files),
        parse_strategy=parse_strategy.value,
        chunk_strategy=chunk_strategy.value,
    )
    
    if dry_run:
        logger.info("DRY RUN - no indexing will occur")
        return stats
    
    # Initialize components
    embedding_model = EmbeddingModelFactory.create_default()
    hybrid_index = HybridIndex(embedding_model=embedding_model)
    chunker = ChunkerFactory.get_chunker(
        strategy=chunk_strategy,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    
    # Process files
    for file_path in tqdm(files, desc="Ingesting documents"):
        try:
            # Step 1: Parse
            logger.info("Parsing document", path=str(file_path))
            doc = DocumentParserFactory.parse(file_path, strategy=parse_strategy)
            stats["files_parsed"] += 1
            
            if not doc.content.strip():
                logger.warning("Empty document, skipping", path=str(file_path))
                continue
            
            # Step 2: Chunk
            chunks = chunker.chunk(doc)
            stats["total_chunks"] += len(chunks)
            
            logger.info(
                "Document parsed and chunked",
                doc_id=doc.doc_id,
                title=doc.title,
                chunks=len(chunks),
            )
            
            # Step 3: Index
            indexed_ids = hybrid_index.add_chunks(chunks)
            stats["indexed_chunks"] += len(indexed_ids)
            
        except Exception as e:
            stats["files_failed"] += 1
            logger.error(
                "Failed to process document",
                path=str(file_path),
                error=str(e),
                exc_info=True,
            )
    
    logger.info("Ingestion complete", **stats)
    return stats


def main():
    setup_logging()
    
    parser = argparse.ArgumentParser(description="Ingest documents into the RAG index")
    parser.add_argument(
        "--source-dir",
        type=str,
        default="./data/raw",
        help="Directory containing source documents",
    )
    parser.add_argument(
        "--parse-strategy",
        type=str,
        choices=["rule_based", "ai_based", "hybrid"],
        default="rule_based",
    )
    parser.add_argument(
        "--chunk-strategy",
        type=str,
        choices=["fixed_size", "sentence", "hierarchical"],
        default="hierarchical",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=settings.chunk_size,
    )
    parser.add_argument(
        "--chunk-overlap",
        type=int,
        default=settings.chunk_overlap,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse without indexing",
    )
    
    args = parser.parse_args()
    
    stats = ingest_documents(
        source_dir=Path(args.source_dir),
        parse_strategy=ParseStrategy(args.parse_strategy),
        chunk_strategy=ChunkingStrategy(args.chunk_strategy),
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
        dry_run=args.dry_run,
    )
    
    print("\n=== Ingestion Summary ===")
    for key, value in stats.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()