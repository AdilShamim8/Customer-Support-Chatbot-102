"""
Embedding model abstraction layer.
Supports OpenAI, Cohere, and local Sentence Transformers.
Includes caching, batching, and retry logic.
"""

import asyncio
import hashlib
import json
from abc import ABC, abstractmethod
from enum import Enum
from typing import Optional

import numpy as np
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from configs.settings import settings

logger = structlog.get_logger(__name__)


class EmbeddingProvider(str, Enum):
    OPENAI = "openai"
    SENTENCE_TRANSFORMERS = "sentence_transformers"
    COHERE = "cohere"


@dataclass
class EmbeddingResult:
    """Result of an embedding operation."""
    texts: list[str]
    embeddings: list[list[float]]
    model: str
    dimension: int
    token_count: int = 0
    
    def as_numpy(self) -> np.ndarray:
        return np.array(self.embeddings, dtype=np.float32)


class BaseEmbeddingModel(ABC):
    """Abstract embedding model interface."""
    
    def __init__(self, model_name: str, dimension: int, batch_size: int = 100):
        self.model_name = model_name
        self.dimension = dimension
        self.batch_size = batch_size
        self._cache: dict[str, list[float]] = {}
    
    @abstractmethod
    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts. Override in subclasses."""
        pass
    
    def embed(self, texts: list[str]) -> EmbeddingResult:
        """Embed texts with batching and caching."""
        if isinstance(texts, str):
            texts = [texts]
        
        # Check cache
        embeddings = []
        uncached_texts = []
        uncached_indices = []
        
        for i, text in enumerate(texts):
            cache_key = self._cache_key(text)
            if cache_key in self._cache:
                embeddings.append((i, self._cache[cache_key]))
            else:
                uncached_texts.append(text)
                uncached_indices.append(i)
        
        # Embed uncached texts in batches
        if uncached_texts:
            new_embeddings = self._embed_in_batches(uncached_texts)
            
            for text, embedding, original_idx in zip(
                uncached_texts, new_embeddings, uncached_indices
            ):
                cache_key = self._cache_key(text)
                self._cache[cache_key] = embedding
                embeddings.append((original_idx, embedding))
        
        # Sort by original index
        embeddings.sort(key=lambda x: x[0])
        final_embeddings = [e for _, e in embeddings]
        
        return EmbeddingResult(
            texts=texts,
            embeddings=final_embeddings,
            model=self.model_name,
            dimension=self.dimension,
        )
    
    def embed_single(self, text: str) -> list[float]:
        """Embed a single text."""
        result = self.embed([text])
        return result.embeddings[0]
    
    def _embed_in_batches(self, texts: list[str]) -> list[list[float]]:
        """Process texts in batches."""
        all_embeddings = []
        
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i:i + self.batch_size]
            logger.debug(
                "Embedding batch",
                batch_num=i // self.batch_size + 1,
                batch_size=len(batch),
            )
            batch_embeddings = self._embed_batch(batch)
            all_embeddings.extend(batch_embeddings)
        
        return all_embeddings
    
    def _cache_key(self, text: str) -> str:
        return hashlib.md5(f"{self.model_name}:{text}".encode()).hexdigest()


class OpenAIEmbeddingModel(BaseEmbeddingModel):
    """
    OpenAI embedding model (text-embedding-3-small/large).
    Recommended for production use with OpenAI backend.
    """
    
    _DIMENSIONS = {
        "text-embedding-3-small": 1536,
        "text-embedding-3-large": 3072,
        "text-embedding-ada-002": 1536,
    }
    
    def __init__(
        self,
        model_name: str = "text-embedding-3-small",
        **kwargs,
    ):
        import openai
        
        dimension = self._DIMENSIONS.get(model_name, 1536)
        super().__init__(model_name, dimension, **kwargs)
        self.client = openai.OpenAI(api_key=settings.openai_api_key)
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type(Exception),
    )
    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Call OpenAI Embeddings API with retry logic."""
        # Clean texts
        cleaned = [t.replace("\n", " ").strip() for t in texts]
        
        response = self.client.embeddings.create(
            model=self.model_name,
            input=cleaned,
        )
        
        return [item.embedding for item in response.data]


class SentenceTransformerEmbeddingModel(BaseEmbeddingModel):
    """
    Local embedding using Sentence Transformers.
    Good for offline/private deployments.
    """
    
    _POPULAR_MODELS = {
        "all-MiniLM-L6-v2": 384,
        "all-mpnet-base-v2": 768,
        "multi-qa-MiniLM-L6-cos-v1": 384,
        "BAAI/bge-large-en-v1.5": 1024,
        "BAAI/bge-base-en-v1.5": 768,
    }
    
    def __init__(
        self,
        model_name: str = "BAAI/bge-large-en-v1.5",
        device: Optional[str] = None,
        **kwargs,
    ):
        from sentence_transformers import SentenceTransformer
        
        dimension = self._POPULAR_MODELS.get(model_name, 768)
        super().__init__(model_name, dimension, **kwargs)
        
        import torch
        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"
        
        logger.info(
            "Loading Sentence Transformer",
            model=model_name,
            device=device,
        )
        self.model = SentenceTransformer(model_name, device=device)
        self.device = device
    
    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        embeddings = self.model.encode(
            texts,
            normalize_embeddings=True,   # L2 normalization
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return embeddings.tolist()


class EmbeddingModelFactory:
    """Factory for creating embedding models."""
    
    @staticmethod
    def create(
        provider: EmbeddingProvider = EmbeddingProvider.OPENAI,
        model_name: Optional[str] = None,
        **kwargs,
    ) -> BaseEmbeddingModel:
        
        if provider == EmbeddingProvider.OPENAI:
            return OpenAIEmbeddingModel(
                model_name=model_name or settings.embedding_model,
                **kwargs,
            )
        elif provider == EmbeddingProvider.SENTENCE_TRANSFORMERS:
            return SentenceTransformerEmbeddingModel(
                model_name=model_name or "BAAI/bge-large-en-v1.5",
                **kwargs,
            )
        else:
            raise ValueError(f"Unsupported embedding provider: {provider}")
    
    @staticmethod
    def create_default() -> BaseEmbeddingModel:
        """Create the default embedding model from settings."""
        return EmbeddingModelFactory.create(
            provider=EmbeddingProvider.OPENAI,
            model_name=settings.embedding_model,
        )