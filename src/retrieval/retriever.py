"""
Core retrieval pipeline orchestrating hybrid search + reranking.
This is the main RAG retrieval component that the generation module calls.
"""

from dataclasses import dataclass, field
from typing import Any, Optional

import structlog

from configs.settings import settings
from src.indexing.hybrid_index import HybridIndex
from src.indexing.vector_store import SearchQuery, SearchResult
from src.retrieval.reranker import BaseReranker, RerankerFactory

logger = structlog.get_logger(__name__)


@dataclass
class RetrievalConfig:
    """Configuration for a retrieval request."""
    top_k_retrieval: int = settings.top_k_retrieval
    top_k_rerank: int = settings.top_k_rerank
    similarity_threshold: float = settings.similarity_threshold
    use_vector: bool = True
    use_keyword: bool = True
    use_reranking: bool = True
    filters: dict[str, Any] = field(default_factory=dict)


@dataclass
class RetrievalResult:
    """Complete retrieval result with provenance."""
    query: str
    chunks: list[SearchResult]
    config: RetrievalConfig
    retrieval_metadata: dict[str, Any] = field(default_factory=dict)
    
    @property
    def context(self) -> str:
        """Format retrieved chunks as a single context string."""
        if not self.chunks:
            return ""
        
        parts = []
        for i, chunk in enumerate(self.chunks, 1):
            source = chunk.metadata.get("title", chunk.doc_id)
            section = chunk.metadata.get("section_title", "")
            header = f"[Source {i}: {source}"
            if section:
                header += f" > {section}"
            header += "]"
            
            parts.append(f"{header}\n{chunk.content}")
        
        return "\n\n---\n\n".join(parts)
    
    @property
    def sources(self) -> list[dict]:
        """Return unique sources for citations."""
        seen = set()
        sources = []
        
        for chunk in self.chunks:
            doc_id = chunk.doc_id
            if doc_id not in seen:
                seen.add(doc_id)
                sources.append({
                    "doc_id": doc_id,
                    "title": chunk.metadata.get("title", "Unknown"),
                    "source": chunk.metadata.get("source", ""),
                    "doc_type": chunk.metadata.get("doc_type", ""),
                })
        
        return sources


class Retriever:
    """
    Main RAG retriever combining hybrid search and reranking.
    
    Pipeline:
        Query → Query Expansion (optional)
              → Hybrid Search (Vector + BM25)
              → RRF Fusion
              → Reranking
              → Context Assembly
    """
    
    def __init__(
        self,
        hybrid_index: Optional[HybridIndex] = None,
        reranker: Optional[BaseReranker] = None,
        enable_query_expansion: bool = False,
    ):
        self.hybrid_index = hybrid_index or HybridIndex()
        self.reranker = reranker or RerankerFactory.create_best_available()
        self.enable_query_expansion = enable_query_expansion
        
        logger.info(
            "Retriever initialized",
            has_reranker=self.reranker is not None,
            query_expansion=enable_query_expansion,
        )
    
    def retrieve(
        self,
        query: str,
        config: Optional[RetrievalConfig] = None,
    ) -> RetrievalResult:
        """
        Full retrieval pipeline for a given query.
        
        Args:
            query: User's question
            config: Optional retrieval configuration
        
        Returns:
            RetrievalResult with ranked chunks and formatted context
        """
        config = config or RetrievalConfig()
        
        logger.info(
            "Starting retrieval",
            query=query[:100],
            top_k=config.top_k_retrieval,
            use_reranking=config.use_reranking,
        )
        
        # Step 1: Optional query expansion
        search_queries = [query]
        if self.enable_query_expansion:
            search_queries = self._expand_query(query)
        
        # Step 2: Hybrid search
        all_results = []
        seen_chunk_ids = set()
        
        for search_query_text in search_queries:
            search_query = SearchQuery(
                text=search_query_text,
                top_k=config.top_k_retrieval,
                filters=config.filters,
                min_score=0.0,    # Filter after reranking
            )
            
            results = self.hybrid_index.search(
                query=search_query,
                use_vector=config.use_vector,
                use_keyword=config.use_keyword,
            )
            
            # Deduplicate across expanded queries
            for r in results:
                if r.chunk_id not in seen_chunk_ids:
                    all_results.append(r)
                    seen_chunk_ids.add(r.chunk_id)
        
        if not all_results:
            logger.warning("No retrieval results found", query=query)
            return RetrievalResult(
                query=query,
                chunks=[],
                config=config,
                retrieval_metadata={"warning": "no_results"},
            )
        
        logger.debug(
            "Initial retrieval complete",
            results_count=len(all_results),
        )
        
        # Step 3: Reranking
        if config.use_reranking and self.reranker and len(all_results) > 1:
            try:
                final_results = self.reranker.rerank(
                    query=query,
                    results=all_results,
                    top_k=config.top_k_rerank,
                )
                retrieval_metadata = {"reranked": True, "reranker": type(self.reranker).__name__}
            except Exception as e:
                logger.error("Reranking failed, using original order", error=str(e))
                final_results = all_results[:config.top_k_rerank]
                retrieval_metadata = {"reranked": False, "rerank_error": str(e)}
        else:
            final_results = all_results[:config.top_k_rerank]
            retrieval_metadata = {"reranked": False}
        
        # Step 4: Apply similarity threshold
        filtered_results = [
            r for r in final_results
            if r.score >= config.similarity_threshold
        ]
        
        # Always return at least 1 result if we have any
        if not filtered_results and final_results:
            filtered_results = [final_results[0]]
        
        logger.info(
            "Retrieval complete",
            initial_count=len(all_results),
            final_count=len(filtered_results),
        )
        
        return RetrievalResult(
            query=query,
            chunks=filtered_results,
            config=config,
            retrieval_metadata={
                **retrieval_metadata,
                "initial_results": len(all_results),
                "final_results": len(filtered_results),
                "queries_used": len(search_queries),
            },
        )
    
    def _expand_query(self, query: str) -> list[str]:
        """
        Simple rule-based query expansion.
        In production, use LLM-based expansion.
        """
        expansions = [query]
        
        # Add question reformulations
        if not query.strip().endswith("?"):
            expansions.append(f"{query}?")
        
        # Remove question words for keyword search
        import re
        stripped = re.sub(
            r'^(what|how|why|when|where|who|can|does|do|is|are)\s+',
            '', query.lower()
        ).strip()
        if stripped and stripped != query.lower():
            expansions.append(stripped)
        
        return list(dict.fromkeys(expansions))  # Deduplicate preserving order
    
    def index_chunks(self, chunks) -> list[str]:
        """Convenience method to add chunks through the retriever."""
        return self.hybrid_index.add_chunks(chunks)
    
    def get_stats(self) -> dict:
        return {
            "hybrid_index": self.hybrid_index.get_stats(),
            "reranker": type(self.reranker).__name__,
        }