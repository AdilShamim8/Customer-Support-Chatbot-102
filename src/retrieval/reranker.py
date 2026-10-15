"""
Reranking module - takes initial retrieval results and reranks them
using a cross-encoder model for higher precision.
Supports Cohere Rerank API and local cross-encoder models.
"""

from abc import ABC, abstractmethod
from typing import Optional

import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from configs.settings import settings
from src.indexing.vector_store import SearchResult

logger = structlog.get_logger(__name__)


class BaseReranker(ABC):
    """Abstract reranker interface."""
    
    @abstractmethod
    def rerank(
        self,
        query: str,
        results: list[SearchResult],
        top_k: int = settings.top_k_rerank,
    ) -> list[SearchResult]:
        pass


class CohereReranker(BaseReranker):
    """
    Cohere Rerank API - production-grade cross-encoder reranking.
    Significantly improves precision over bi-encoder retrieval.
    """
    
    def __init__(
        self,
        model: str = settings.reranker_model,
        api_key: Optional[str] = None,
    ):
        import cohere
        
        self.model = model
        self.client = cohere.Client(
            api_key=api_key or settings.cohere_api_key
        )
        logger.info("Cohere reranker initialized", model=model)
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=8),
    )
    def rerank(
        self,
        query: str,
        results: list[SearchResult],
        top_k: int = settings.top_k_rerank,
    ) -> list[SearchResult]:
        if not results:
            return []
        
        documents = [r.content for r in results]
        
        response = self.client.rerank(
            query=query,
            documents=documents,
            model=self.model,
            top_n=min(top_k, len(results)),
            return_documents=True,
        )
        
        reranked = []
        for rank, item in enumerate(response.results):
            original = results[item.index]
            reranked.append(SearchResult(
                chunk_id=original.chunk_id,
                doc_id=original.doc_id,
                content=original.content,
                score=item.relevance_score,
                metadata={
                    **original.metadata,
                    "rerank_score": item.relevance_score,
                    "original_rank": original.rank,
                    "original_score": original.score,
                },
                rank=rank,
            ))
        
        logger.debug(
            "Cohere reranking complete",
            input_count=len(results),
            output_count=len(reranked),
        )
        
        return reranked


class CrossEncoderReranker(BaseReranker):
    """
    Local cross-encoder reranker using sentence-transformers.
    No API costs, runs on GPU/CPU. Good for private deployments.
    """
    
    def __init__(
        self,
        model_name: str = "cross-encoder/ms-marco-MiniLM-L-12-v2",
        device: Optional[str] = None,
    ):
        from sentence_transformers import CrossEncoder
        import torch
        
        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"
        
        self.model = CrossEncoder(model_name, device=device)
        self.model_name = model_name
        logger.info(
            "Cross-encoder reranker loaded",
            model=model_name,
            device=device,
        )
    
    def rerank(
        self,
        query: str,
        results: list[SearchResult],
        top_k: int = settings.top_k_rerank,
    ) -> list[SearchResult]:
        if not results:
            return []
        
        # Cross-encoder takes (query, document) pairs
        pairs = [(query, r.content) for r in results]
        scores = self.model.predict(pairs, show_progress_bar=False)
        
        # Pair results with cross-encoder scores
        scored = list(zip(results, scores))
        scored.sort(key=lambda x: x[1], reverse=True)
        
        reranked = []
        for rank, (result, score) in enumerate(scored[:top_k]):
            reranked.append(SearchResult(
                chunk_id=result.chunk_id,
                doc_id=result.doc_id,
                content=result.content,
                score=float(score),
                metadata={
                    **result.metadata,
                    "rerank_score": float(score),
                    "original_rank": result.rank,
                },
                rank=rank,
            ))
        
        return reranked


class FlashRankReranker(BaseReranker):
    """
    FlashRank - ultra-fast local reranker.
    Best for low-latency production environments.
    """
    
    def __init__(self, model_name: str = "ms-marco-MiniLM-L-12-v2"):
        from flashrank import Ranker, RerankRequest
        
        self.ranker = Ranker(model_name=model_name, cache_dir="/tmp/flashrank")
        self.RerankRequest = RerankRequest
        logger.info("FlashRank reranker initialized", model=model_name)
    
    def rerank(
        self,
        query: str,
        results: list[SearchResult],
        top_k: int = settings.top_k_rerank,
    ) -> list[SearchResult]:
        if not results:
            return []
        
        passages = [
            {"id": r.chunk_id, "text": r.content, "meta": r.metadata}
            for r in results
        ]
        
        rerank_request = self.RerankRequest(query=query, passages=passages)
        reranked_passages = self.ranker.rerank(rerank_request)
        
        # Map back to SearchResult objects
        id_to_result = {r.chunk_id: r for r in results}
        
        reranked = []
        for rank, passage in enumerate(reranked_passages[:top_k]):
            original = id_to_result.get(passage["id"])
            if original:
                reranked.append(SearchResult(
                    chunk_id=original.chunk_id,
                    doc_id=original.doc_id,
                    content=original.content,
                    score=passage.get("score", 0.0),
                    metadata={
                        **original.metadata,
                        "rerank_score": passage.get("score", 0.0),
                        "original_rank": original.rank,
                    },
                    rank=rank,
                ))
        
        return reranked


class RerankerFactory:
    """Factory for creating rerankers based on availability and preference."""
    
    @staticmethod
    def create(reranker_type: str = "cohere", **kwargs) -> BaseReranker:
        rerankers = {
            "cohere": CohereReranker,
            "cross_encoder": CrossEncoderReranker,
            "flashrank": FlashRankReranker,
        }
        
        cls = rerankers.get(reranker_type)
        if not cls:
            raise ValueError(f"Unknown reranker: {reranker_type}")
        
        return cls(**kwargs)
    
    @staticmethod
    def create_best_available() -> BaseReranker:
        """Create the best available reranker based on configuration."""
        if settings.cohere_api_key:
            logger.info("Using Cohere reranker")
            return CohereReranker()
        else:
            logger.info("Using local FlashRank reranker")
            return FlashRankReranker()