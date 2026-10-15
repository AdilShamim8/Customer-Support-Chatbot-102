"""Unit tests for chunking strategies."""

import pytest
from src.parsing.chunking import (
    ChunkingStrategy,
    ChunkerFactory,
    FixedSizeChunker,
    HierarchicalChunker,
    SentenceChunker,
)
from src.parsing.document_parser import DocumentType, ParsedDocument


def make_doc(content: str, sections: list = None) -> ParsedDocument:
    return ParsedDocument(
        doc_id="test_doc_001",
        source_path="/tmp/test.pdf",
        doc_type=DocumentType.PDF,
        title="Test Document",
        content=content,
        sections=sections or [],
    )


class TestFixedSizeChunker:
    def test_chunks_long_document(self):
        doc = make_doc("word " * 500)
        chunker = FixedSizeChunker(chunk_size=100, chunk_overlap=20)
        chunks = chunker.chunk(doc)
        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk.content) <= 150   # Allow some variance

    def test_chunk_ids_are_unique(self):
        doc = make_doc("word " * 500)
        chunker = FixedSizeChunker(chunk_size=100)
        chunks = chunker.chunk(doc)
        ids = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids))

    def test_short_document_one_chunk(self):
        doc = make_doc("This is a short document with few words.")
        chunker = FixedSizeChunker(chunk_size=512)
        chunks = chunker.chunk(doc)
        assert len(chunks) == 1

    def test_chunk_metadata_preserved(self):
        doc = make_doc("word " * 100)
        chunker = FixedSizeChunker(chunk_size=100)
        chunks = chunker.chunk(doc)
        for chunk in chunks:
            assert chunk.metadata.get("doc_id") == "test_doc_001"
            assert chunk.metadata.get("title") == "Test Document"


class TestHierarchicalChunker:
    def test_respects_section_boundaries(self):
        sections = [
            {"title": "Section 1", "content": "Content of section one. " * 20},
            {"title": "Section 2", "content": "Content of section two. " * 20},
        ]
        doc = make_doc(
            content="Section 1\nContent one\n\nSection 2\nContent two",
            sections=sections,
        )
        chunker = HierarchicalChunker(chunk_size=200)
        chunks = chunker.chunk(doc)

        section_titles = {c.section_title for c in chunks if c.section_title}
        assert "Section 1" in section_titles
        assert "Section 2" in section_titles

    def test_context_prepended_to_chunks(self):
        sections = [
            {"title": "FAQ", "content": "Answer to common questions. " * 30},
        ]
        doc = make_doc(
            content="FAQ\nAnswer to common questions.",
            sections=sections,
        )
        chunker = HierarchicalChunker(chunk_size=100)
        chunks = chunker.chunk(doc)

        for chunk in chunks:
            if chunk.section_title:
                assert "[Section:" in chunk.content


class TestChunkerFactory:
    def test_creates_correct_chunker(self):
        chunker = ChunkerFactory.get_chunker(ChunkingStrategy.FIXED_SIZE)
        assert isinstance(chunker, FixedSizeChunker)

        chunker = ChunkerFactory.get_chunker(ChunkingStrategy.HIERARCHICAL)
        assert isinstance(chunker, HierarchicalChunker)

    def test_raises_on_unknown_strategy(self):
        with pytest.raises(ValueError):
            ChunkerFactory.get_chunker("unknown_strategy")