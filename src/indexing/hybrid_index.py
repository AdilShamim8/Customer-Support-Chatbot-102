"""
Hybrid Index combining Vector Search + BM25/Elasticsearch.
Uses Reciprocal Rank Fusion (RRF) to merge results from both indices.
This is the gold standard for RAG retrieval quality.
"""

from dataclasses import dataclass, field
from typing import Optional

import structlog

from configs.settings import settings
from src.indexing.vector_store import (
    BaseVectorStore,
    SearchQuery,
    SearchResult,
    VectorStoreFactory,
)
from src.indexing.keyword_index import BaseKeywordIndex, BM25Index
from src.indexing.embeddings import BaseEmbeddingModel, EmbeddingModelFactory
from src.parsing.chunking import DocumentChunk

logger = structlog.get_logger(__name__)


def reciprocal_rank_fusion(
    result_lists: list[list[SearchResult]],
    k: int = 60,
    weights: Optional[list[float]] = None,
) -> list[SearchResult]:
    """
    Reciprocal Rank Fusion - merge multiple ranked lists.
    
    RRF Score: sum(1 / (k + rank)) weighted by source weight.
    
    Args:
        result_lists: Lists of SearchResult from different retrieval methods
        k: Ranking constant (default 60 from original RRF paper)
        weights: Per-list weights (default equal weights)
    
    Returns:
        Merged and re-ranked list of SearchResults
    """
    if not result_lists:
        return []
    
    if weights is None:
        weights = [1.0] * len(result_lists)
    
    assert len(weights) == len(result_lists), "Weights must match result lists"
    
    # Accumulate RRF scores
    chunk_scores: dict[str, float] = {}
    chunk_results: dict[str, SearchResult] = {}
    
    for result_list, weight in zip(result_lists, weights):
        for rank, result in enumerate(result_list):
            rrf_score = weight * (1.0 / (k + rank + 1))
            
            if result.chunk_id in chunk_scores:
                chunk_scores[result.chunk_id] += rrf_score
            else:
                chunk_scores[result.chunk_id] = rrf_score
                chunk_results[result.chunk_id] = result
    
    # Sort by combined RRF score
    sorted_ids = sorted(chunk_scores.keys(), key=lambda x: chunk_scores[x], reverse=True)
    
    merged = []
    for rank, chunk_id in enumerate(sorted_ids):
        result = chunk_results[chunk_id]
        merged.append(SearchResult(
            chunk_id=result.chunk_id,
            doc_id=result.doc_id,
            content=result.content,
            score=chunk_scores[chunk_id],
            metadata=result.metadata,
            rank=rank,
        ))
    
    return merged


class HybridIndex:
    """
    Hybrid search combining dense vector search with sparse BM25.
    Uses Reciprocal Rank Fusion for result merging.
    
    Architecture:
        Query → [Vector Search | BM25 Search] → RRF Fusion → Reranker → Results
    """
    
    def __init__(
        self,
        vector_store: Optional[BaseVectorStore] = None,
        keyword_index: Optional[BaseKeywordIndex] = None,
        embedding_model: Optional[BaseEmbeddingModel] = None,
        vector_weight: float = 0.7,
        keyword_weight: float = 0.3,
        rrf_k: int = 60,
    ):
        self.embedding_model = (
            embedding_model or EmbeddingModelFactory.create_default()
        )
        self.vector_store = vector_store or VectorStoreFactory.create_default(
            embedding_model=self.embedding_model
        )
        self.keyword_index = keyword_index or BM25Index()
        self.vector_weight = vector_weight
        self.keyword_weight = keyword_weight
        self.rrf_k = rrf_k
        
        self._doc_registry: dict[str, list[str]] = {}  # doc_id -> chunk_ids
        
        logger.info(
            "HybridIndex initialized",
            vector_weight=vector_weight,
            keyword_weight=keyword_weight,
        )
    
    def add_chunks(self, chunks: list[DocumentChunk]) -> list[str]:
        """Index chunks in both vector and keyword stores."""
        if not chunks:
            return []
        
        logger.info("Adding chunks to hybrid index", count=len(chunks))
        
        # Add to vector store
        vector_ids = self.vector_store.add_chunks(chunks)
        
        # Add to keyword index
        self.keyword_index.add_chunks(chunks)
        
        # Update document registry
        for chunk in chunks:
            if chunk.doc_id not in self._doc_registry:
                self._doc_registry[chunk.doc_id] = []
            self._doc_registry[chunk.doc_id].append(chunk.chunk_id)
        
        logger.info(
            "Hybrid index updated",
            chunks_added=len(chunks),
            total_docs=len(self._doc_registry),
            vector_store_count=self.vector_store.count(),
            keyword_index_count=self.keyword_index.count(),
        )
        
        return vector_ids
    
    def search(
        self,
        query: SearchQuery,
        use_vector: bool = True,
        use_keyword: bool = True,
    ) -> list[SearchResult]:
        """
        Hybrid search with configurable source selection.
        
        Args:
            query: Search query with text, top_k, and filters
            use_vector: Include vector similarity search
            use_keyword: Include BM25 keyword search
        
        Returns:
            Merged and ranked results
        """
        result_lists = []
        weights = []
        
        # Vector search
        if use_vector:
            try:
                # Fetch more candidates for fusion
                vector_query = SearchQuery(
                    text=query.text,
                    top_k=query.top_k * 2,
                    filters=query.filters,
                    min_score=0.0,       # Don't filter before fusion
                )
                vector_results = self.vector_store.search(vector_query)
                result_lists.append(vector_results)
                weights.append(self.vector_weight)
                
                logger.debug(
                    "Vector search complete",
                    results=len(vector_results),
                )
            except Exception as e:
                logger.error("Vector search failed", error=str(e))
        
        # Keyword search
        if use_keyword:
            try:
                keyword_query = SearchQuery(
                    text=query.text,
                    top_k=query.top_k * 2,
                    filters=query.filters,
                    min_score=0.0,
                )
                keyword_results = self.keyword_index.search(keyword_query)
                result_lists.append(keyword_results)
                weights.append(self.keyword_weight)
                
                logger.debug(
                    "Keyword search complete",
                    results=len(keyword_results),
                )
            except Exception as e:
                logger.error("Keyword search failed", error=str(e))
        
        if not result_lists:
            return []
        
        # Fuse results using RRF
        if len(result_lists) == 1:
            merged = result_lists[0]
        else:
            merged = reciprocal_rank_fusion(
                result_lists,
                k=self.rrf_k,
                weights=weights,
            )
        
        # Apply top_k and score threshold
        filtered = [
            r for r in merged[:query.top_k]
            if r.score >= query.min_score
        ]
        
        logger.debug(
            "Hybrid search complete",
            total_before_filter=len(merged),
            total_after_filter=len(filtered),
        )
        
        return filtered
    
    def delete_document(self, doc_id: str) -> int:
        """Delete document from all indices."""
        v_deleted = self.vector_store.delete_document(doc_id)
        k_deleted = self.keyword_index.delete_document(doc_id)
        self._doc_registry.pop(doc_id, None)
        
        logger.info(
            "Document deleted from hybrid index",
            doc_id=doc_id,
            vector_deleted=v_deleted,
            keyword_deleted=k_deleted,
        )
        return v_deleted
    
    def get_stats(self) -> dict:
        return {
            "vector_store_count": self.vector_store.count(),
            "keyword_index_count": self.keyword_index.count(),
            "document_count": len(self._doc_registry),
            "vector_weight": self.vector_weight,
            "keyword_weight": self.keyword_weight,
        }