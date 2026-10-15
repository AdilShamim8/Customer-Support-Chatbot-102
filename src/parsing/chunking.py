"""
Comprehensive chunking strategies for RAG pipelines.
Implements: Fixed-size, Sentence, Semantic, and Hierarchical chunking.
"""

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

import structlog
import tiktoken

from configs.settings import settings
from src.parsing.document_parser import ParsedDocument

logger = structlog.get_logger(__name__)


class ChunkingStrategy(str, Enum):
    FIXED_SIZE = "fixed_size"         # Character/token-based fixed windows
    SENTENCE = "sentence"              # Sentence boundary-aware
    PARAGRAPH = "paragraph"            # Paragraph-based
    SEMANTIC = "semantic"              # Semantic similarity-based
    HIERARCHICAL = "hierarchical"      # Multi-level (document > section > chunk)
    SLIDING_WINDOW = "sliding_window"  # Overlapping windows


@dataclass
class DocumentChunk:
    """A chunk of a parsed document with full provenance tracking."""
    chunk_id: str
    doc_id: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    
    # Positional info
    chunk_index: int = 0
    total_chunks: int = 0
    start_char: int = 0
    end_char: int = 0
    
    # Hierarchical context
    section_title: Optional[str] = None
    section_index: Optional[int] = None
    parent_chunk_id: Optional[str] = None
    
    # Token info
    token_count: int = 0
    
    @property
    def char_count(self) -> int:
        return len(self.content)
    
    def to_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "doc_id": self.doc_id,
            "content": self.content,
            "metadata": self.metadata,
            "chunk_index": self.chunk_index,
            "total_chunks": self.total_chunks,
            "start_char": self.start_char,
            "end_char": self.end_char,
            "section_title": self.section_title,
            "token_count": self.token_count,
        }


class TokenCounter:
    """Counts tokens using tiktoken for accurate LLM context management."""
    
    def __init__(self, model: str = "gpt-4"):
        try:
            self.encoder = tiktoken.encoding_for_model(model)
        except KeyError:
            self.encoder = tiktoken.get_encoding("cl100k_base")
    
    def count(self, text: str) -> int:
        return len(self.encoder.encode(text))
    
    def truncate(self, text: str, max_tokens: int) -> str:
        tokens = self.encoder.encode(text)
        if len(tokens) <= max_tokens:
            return text
        return self.encoder.decode(tokens[:max_tokens])


class BaseChunker(ABC):
    """Abstract base chunker."""
    
    def __init__(
        self,
        chunk_size: int = settings.chunk_size,
        chunk_overlap: int = settings.chunk_overlap,
        min_chunk_size: int = settings.min_chunk_size,
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size
        self.token_counter = TokenCounter()
    
    @abstractmethod
    def chunk(self, document: ParsedDocument) -> list[DocumentChunk]:
        pass
    
    def _make_chunk_id(self, doc_id: str, index: int) -> str:
        return f"{doc_id}_chunk_{index:04d}"
    
    def _build_base_metadata(self, document: ParsedDocument) -> dict:
        return {
            "source": document.source_path,
            "doc_type": document.doc_type.value,
            "title": document.title,
            "doc_id": document.doc_id,
            **document.metadata,
        }
    
    def _filter_short_chunks(
        self, chunks: list[DocumentChunk]
    ) -> list[DocumentChunk]:
        """Remove chunks that are too short to be meaningful."""
        filtered = [c for c in chunks if len(c.content) >= self.min_chunk_size]
        removed = len(chunks) - len(filtered)
        if removed > 0:
            logger.debug("Filtered short chunks", count=removed)
        return filtered


class FixedSizeChunker(BaseChunker):
    """
    Fixed-size chunking with character overlap.
    Simple and fast but may split mid-sentence.
    """
    
    def chunk(self, document: ParsedDocument) -> list[DocumentChunk]:
        logger.debug(
            "Fixed-size chunking",
            doc_id=document.doc_id,
            size=self.chunk_size,
        )
        
        content = document.content
        base_metadata = self._build_base_metadata(document)
        chunks = []
        start = 0
        index = 0
        
        while start < len(content):
            end = start + self.chunk_size
            chunk_text = content[start:end]
            
            # Try to end at a word boundary
            if end < len(content) and not content[end].isspace():
                last_space = chunk_text.rfind(' ')
                if last_space > self.chunk_size // 2:
                    end = start + last_space
                    chunk_text = content[start:end]
            
            chunks.append(DocumentChunk(
                chunk_id=self._make_chunk_id(document.doc_id, index),
                doc_id=document.doc_id,
                content=chunk_text.strip(),
                metadata=base_metadata.copy(),
                chunk_index=index,
                start_char=start,
                end_char=end,
                token_count=self.token_counter.count(chunk_text),
            ))
            
            start = max(start + 1, end - self.chunk_overlap)
            index += 1
        
        # Update total_chunks
        for chunk in chunks:
            chunk.total_chunks = len(chunks)
        
        return self._filter_short_chunks(chunks)


class SentenceChunker(BaseChunker):
    """
    Sentence-aware chunking - respects sentence boundaries.
    Better semantic coherence than fixed-size.
    """
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._sentence_pattern = re.compile(
            r'(?<=[.!?])\s+(?=[A-Z])|(?<=[.!?])\n'
        )
    
    def chunk(self, document: ParsedDocument) -> list[DocumentChunk]:
        logger.debug("Sentence chunking", doc_id=document.doc_id)
        
        sentences = self._split_into_sentences(document.content)
        base_metadata = self._build_base_metadata(document)
        chunks = []
        current_sentences = []
        current_size = 0
        index = 0
        start_char = 0
        
        for sentence in sentences:
            sentence_size = len(sentence)
            
            if (
                current_size + sentence_size > self.chunk_size
                and current_sentences
            ):
                # Emit current chunk
                chunk_text = " ".join(current_sentences)
                end_char = start_char + len(chunk_text)
                
                chunks.append(DocumentChunk(
                    chunk_id=self._make_chunk_id(document.doc_id, index),
                    doc_id=document.doc_id,
                    content=chunk_text.strip(),
                    metadata=base_metadata.copy(),
                    chunk_index=index,
                    start_char=start_char,
                    end_char=end_char,
                    token_count=self.token_counter.count(chunk_text),
                ))
                
                # Handle overlap - keep last few sentences
                overlap_sentences = self._get_overlap_sentences(
                    current_sentences
                )
                start_char = end_char - sum(len(s) for s in overlap_sentences)
                current_sentences = overlap_sentences
                current_size = sum(len(s) for s in overlap_sentences)
                index += 1
            
            current_sentences.append(sentence)
            current_size += sentence_size
        
        # Final chunk
        if current_sentences:
            chunk_text = " ".join(current_sentences)
            chunks.append(DocumentChunk(
                chunk_id=self._make_chunk_id(document.doc_id, index),
                doc_id=document.doc_id,
                content=chunk_text.strip(),
                metadata=base_metadata.copy(),
                chunk_index=index,
                start_char=start_char,
                end_char=start_char + len(chunk_text),
                total_chunks=index + 1,
                token_count=self.token_counter.count(chunk_text),
            ))
        
        for chunk in chunks:
            chunk.total_chunks = len(chunks)
        
        return self._filter_short_chunks(chunks)
    
    def _split_into_sentences(self, text: str) -> list[str]:
        """Split text into sentences using regex patterns."""
        # Split on sentence-ending punctuation followed by whitespace + capital
        sentences = re.split(
            r'(?<=[.!?])\s+(?=[A-Z"])|(?<=\n\n)',
            text.strip()
        )
        return [s.strip() for s in sentences if s.strip()]
    
    def _get_overlap_sentences(
        self, sentences: list[str]
    ) -> list[str]:
        """Get sentences for overlap based on character count."""
        overlap_sentences = []
        overlap_size = 0
        
        for sentence in reversed(sentences):
            if overlap_size + len(sentence) > self.chunk_overlap:
                break
            overlap_sentences.insert(0, sentence)
            overlap_size += len(sentence)
        
        return overlap_sentences


class HierarchicalChunker(BaseChunker):
    """
    Hierarchical chunking: Document → Section → Paragraph → Chunk.
    Preserves document structure and enables parent-child retrieval.
    This is the most effective strategy for structured documents.
    """
    
    def chunk(self, document: ParsedDocument) -> list[DocumentChunk]:
        logger.debug("Hierarchical chunking", doc_id=document.doc_id)
        
        all_chunks = []
        base_metadata = self._build_base_metadata(document)
        
        if document.sections:
            # Process each section independently
            for sec_idx, section in enumerate(document.sections):
                section_title = section.get("title", f"Section {sec_idx + 1}")
                section_content = section.get("content", "")
                
                if not section_content.strip():
                    continue
                
                # Create section-level parent chunk (summary chunk)
                parent_chunk_id = self._make_chunk_id(
                    document.doc_id, len(all_chunks)
                )
                
                section_metadata = {
                    **base_metadata,
                    "section_title": section_title,
                    "section_index": sec_idx,
                    "chunk_type": "section_header",
                }
                
                # Split section into sub-chunks
                sub_chunks = self._chunk_section(
                    content=section_content,
                    doc_id=document.doc_id,
                    section_title=section_title,
                    section_index=sec_idx,
                    parent_chunk_id=parent_chunk_id,
                    base_metadata=section_metadata,
                    start_index=len(all_chunks),
                )
                
                all_chunks.extend(sub_chunks)
        else:
            # Fallback: treat entire document as one section
            sub_chunks = self._chunk_section(
                content=document.content,
                doc_id=document.doc_id,
                section_title=document.title,
                section_index=0,
                parent_chunk_id=None,
                base_metadata=base_metadata,
                start_index=0,
            )
            all_chunks.extend(sub_chunks)
        
        # Update totals
        total = len(all_chunks)
        for chunk in all_chunks:
            chunk.total_chunks = total
        
        logger.info(
            "Hierarchical chunking complete",
            doc_id=document.doc_id,
            total_chunks=total,
            sections=len(document.sections),
        )
        
        return self._filter_short_chunks(all_chunks)
    
    def _chunk_section(
        self,
        content: str,
        doc_id: str,
        section_title: str,
        section_index: int,
        parent_chunk_id: Optional[str],
        base_metadata: dict,
        start_index: int,
    ) -> list[DocumentChunk]:
        """Split a section into chunks using paragraph-aware splitting."""
        
        # Split by paragraph (double newline)
        paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]
        
        chunks = []
        current_paragraphs = []
        current_size = 0
        
        for para in paragraphs:
            para_size = len(para)
            
            if current_size + para_size > self.chunk_size and current_paragraphs:
                chunk_text = "\n\n".join(current_paragraphs)
                # Prepend section title for context
                contextualized = (
                    f"[Section: {section_title}]\n\n{chunk_text}"
                    if section_title
                    else chunk_text
                )
                
                chunk_idx = start_index + len(chunks)
                chunks.append(DocumentChunk(
                    chunk_id=self._make_chunk_id(doc_id, chunk_idx),
                    doc_id=doc_id,
                    content=contextualized,
                    metadata={**base_metadata, "has_section_context": True},
                    chunk_index=chunk_idx,
                    section_title=section_title,
                    section_index=section_index,
                    parent_chunk_id=parent_chunk_id,
                    token_count=self.token_counter.count(contextualized),
                ))
                
                current_paragraphs = []
                current_size = 0
            
            current_paragraphs.append(para)
            current_size += para_size
        
        # Remaining paragraphs
        if current_paragraphs:
            chunk_text = "\n\n".join(current_paragraphs)
            contextualized = (
                f"[Section: {section_title}]\n\n{chunk_text}"
                if section_title
                else chunk_text
            )
            chunk_idx = start_index + len(chunks)
            chunks.append(DocumentChunk(
                chunk_id=self._make_chunk_id(doc_id, chunk_idx),
                doc_id=doc_id,
                content=contextualized,
                metadata={**base_metadata, "has_section_context": True},
                chunk_index=chunk_idx,
                section_title=section_title,
                section_index=section_index,
                parent_chunk_id=parent_chunk_id,
                token_count=self.token_counter.count(contextualized),
            ))
        
        return chunks


class ChunkerFactory:
    """Factory for creating chunkers based on strategy."""
    
    _CHUNKERS = {
        ChunkingStrategy.FIXED_SIZE: FixedSizeChunker,
        ChunkingStrategy.SENTENCE: SentenceChunker,
        ChunkingStrategy.HIERARCHICAL: HierarchicalChunker,
    }
    
    @classmethod
    def get_chunker(
        cls,
        strategy: ChunkingStrategy = ChunkingStrategy.HIERARCHICAL,
        **kwargs,
    ) -> BaseChunker:
        chunker_class = cls._CHUNKERS.get(strategy)
        if not chunker_class:
            raise ValueError(f"Unknown chunking strategy: {strategy}")
        return chunker_class(**kwargs)
    
    @classmethod
    def chunk_document(
        cls,
        document: ParsedDocument,
        strategy: ChunkingStrategy = ChunkingStrategy.HIERARCHICAL,
        **kwargs,
    ) -> list[DocumentChunk]:
        chunker = cls.get_chunker(strategy, **kwargs)
        return chunker.chunk(document)