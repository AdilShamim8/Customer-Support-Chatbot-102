"""
Vector Store abstraction layer.
Supports ChromaDB (local), FAISS (in-memory/disk), and Pinecone (cloud).
Handles CRUD operations, similarity search, and index management.
"""

import os
import pickle
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import numpy as np
import structlog

from configs.settings import settings, VectorStoreType
from src.indexing.embeddings import BaseEmbeddingModel, EmbeddingModelFactory
from src.parsing.chunking import DocumentChunk

logger = structlog.get_logger(__name__)


@dataclass
class SearchResult:
    """A single vector search result with score and metadata."""
    chunk_id: str
    doc_id: str
    content: str
    score: float                          # Similarity score (0-1)
    metadata: dict[str, Any] = field(default_factory=dict)
    rank: int = 0
    
    def to_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "doc_id": self.doc_id,
            "content": self.content,
            "score": self.score,
            "metadata": self.metadata,
            "rank": self.rank,
        }


@dataclass
class SearchQuery:
    """A search query with optional filters."""
    text: str
    top_k: int = settings.top_k_retrieval
    filters: dict[str, Any] = field(default_factory=dict)
    min_score: float = settings.similarity_threshold


class BaseVectorStore(ABC):
    """Abstract vector store interface."""
    
    def __init__(self, embedding_model: Optional[BaseEmbeddingModel] = None):
        self.embedding_model = embedding_model or EmbeddingModelFactory.create_default()
    
    @abstractmethod
    def add_chunks(self, chunks: list[DocumentChunk]) -> list[str]:
        """Add chunks to the store. Returns list of stored IDs."""
        pass
    
    @abstractmethod
    def search(self, query: SearchQuery) -> list[SearchResult]:
        """Search for similar chunks."""
        pass
    
    @abstractmethod
    def delete_document(self, doc_id: str) -> int:
        """Delete all chunks for a document. Returns count deleted."""
        pass
    
    @abstractmethod
    def get_chunk(self, chunk_id: str) -> Optional[SearchResult]:
        """Retrieve a specific chunk by ID."""
        pass
    
    @abstractmethod
    def count(self) -> int:
        """Return total number of chunks in the store."""
        pass
    
    @abstractmethod
    def clear(self) -> None:
        """Clear all data from the store."""
        pass
    
    def _embed_chunks(self, chunks: list[DocumentChunk]) -> list[list[float]]:
        """Embed chunks with progress logging."""
        texts = [chunk.content for chunk in chunks]
        logger.info("Embedding chunks", count=len(texts))
        result = self.embedding_model.embed(texts)
        return result.embeddings
    
    def _embed_query(self, query_text: str) -> list[float]:
        """Embed a single query text."""
        return self.embedding_model.embed_single(query_text)


class ChromaVectorStore(BaseVectorStore):
    """
    ChromaDB vector store - best for local development and testing.
    Persists to disk, supports metadata filtering.
    """
    
    def __init__(
        self,
        collection_name: str = settings.chroma_collection,
        persist_directory: str = "./data/chroma",
        embedding_model: Optional[BaseEmbeddingModel] = None,
    ):
        super().__init__(embedding_model)
        import chromadb
        from chromadb.config import Settings as ChromaSettings
        
        self.collection_name = collection_name
        
        # Initialize persistent client
        self.client = chromadb.PersistentClient(
            path=persist_directory,
            settings=ChromaSettings(
                anonymized_telemetry=False,
                allow_reset=True,
            ),
        )
        
        # Get or create collection
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},    # Cosine similarity
        )
        
        logger.info(
            "ChromaDB initialized",
            collection=collection_name,
            persist_dir=persist_directory,
            existing_count=self.collection.count(),
        )
    
    def add_chunks(self, chunks: list[DocumentChunk]) -> list[str]:
        if not chunks:
            return []
        
        # Batch processing to avoid memory issues
        BATCH_SIZE = 100
        all_ids = []
        
        for batch_start in range(0, len(chunks), BATCH_SIZE):
            batch = chunks[batch_start:batch_start + BATCH_SIZE]
            
            # Embed batch
            embeddings = self._embed_chunks(batch)
            
            # Prepare Chroma data
            ids = [chunk.chunk_id for chunk in batch]
            documents = [chunk.content for chunk in batch]
            metadatas = []
            
            for chunk in batch:
                # Chroma requires flat metadata (no nested dicts)
                flat_meta = self._flatten_metadata(chunk)
                metadatas.append(flat_meta)
            
            # Upsert to handle re-indexing
            self.collection.upsert(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas,
            )
            
            all_ids.extend(ids)
            logger.debug(
                "Batch upserted to ChromaDB",
                batch_size=len(batch),
                total_so_far=len(all_ids),
            )
        
        logger.info(
            "Chunks added to ChromaDB",
            total=len(all_ids),
            collection=self.collection_name,
        )
        return all_ids
    
    def search(self, query: SearchQuery) -> list[SearchResult]:
        query_embedding = self._embed_query(query.text)
        
        # Build where clause from filters
        where = self._build_where_clause(query.filters)
        
        query_params = {
            "query_embeddings": [query_embedding],
            "n_results": min(query.top_k, self.collection.count() or 1),
            "include": ["documents", "metadatas", "distances"],
        }
        
        if where:
            query_params["where"] = where
        
        results = self.collection.query(**query_params)
        
        search_results = []
        
        for i, (chunk_id, document, metadata, distance) in enumerate(zip(
            results["ids"][0],
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        )):
            # Convert cosine distance to similarity (distance range: 0-2)
            similarity = 1 - (distance / 2)
            
            if similarity < query.min_score:
                continue
            
            search_results.append(SearchResult(
                chunk_id=chunk_id,
                doc_id=metadata.get("doc_id", ""),
                content=document,
                score=similarity,
                metadata=metadata,
                rank=i,
            ))
        
        return search_results
    
    def delete_document(self, doc_id: str) -> int:
        """Delete all chunks for a given document."""
        results = self.collection.get(
            where={"doc_id": doc_id},
            include=["documents"],
        )
        
        if results["ids"]:
            self.collection.delete(ids=results["ids"])
            logger.info(
                "Document deleted from ChromaDB",
                doc_id=doc_id,
                chunks_deleted=len(results["ids"]),
            )
            return len(results["ids"])
        return 0
    
    def get_chunk(self, chunk_id: str) -> Optional[SearchResult]:
        results = self.collection.get(
            ids=[chunk_id],
            include=["documents", "metadatas"],
        )
        
        if not results["ids"]:
            return None
        
        return SearchResult(
            chunk_id=chunk_id,
            doc_id=results["metadatas"][0].get("doc_id", ""),
            content=results["documents"][0],
            score=1.0,
            metadata=results["metadatas"][0],
        )
    
    def count(self) -> int:
        return self.collection.count()
    
    def clear(self) -> None:
        self.client.delete_collection(self.collection_name)
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        logger.warning("ChromaDB collection cleared", collection=self.collection_name)
    
    def _flatten_metadata(self, chunk: DocumentChunk) -> dict:
        """Flatten nested metadata for ChromaDB compatibility."""
        flat = {
            "doc_id": chunk.doc_id,
            "chunk_index": chunk.chunk_index,
            "total_chunks": chunk.total_chunks,
            "token_count": chunk.token_count,
        }
        
        if chunk.section_title:
            flat["section_title"] = chunk.section_title
        if chunk.section_index is not None:
            flat["section_index"] = chunk.section_index
        if chunk.parent_chunk_id:
            flat["parent_chunk_id"] = chunk.parent_chunk_id
        
        # Add flat metadata fields (skip nested dicts)
        for k, v in chunk.metadata.items():
            if isinstance(v, (str, int, float, bool)) and v is not None:
                flat[k] = v
        
        return flat
    
    def _build_where_clause(self, filters: dict) -> Optional[dict]:
        """Convert filter dict to Chroma where clause."""
        if not filters:
            return None
        
        if len(filters) == 1:
            key, value = next(iter(filters.items()))
            return {key: {"$eq": value}}
        
        # Multiple filters with AND
        return {
            "$and": [
                {k: {"$eq": v}} for k, v in filters.items()
            ]
        }


class FAISSVectorStore(BaseVectorStore):
    """
    FAISS vector store - best for high-performance similarity search.
    Supports both flat (exact) and IVF (approximate) indices.
    Can be persisted to disk.
    """
    
    def __init__(
        self,
        dimension: int = settings.embedding_dimension,
        index_type: str = "flat",           # "flat" or "ivf"
        persist_path: Optional[str] = None,
        embedding_model: Optional[BaseEmbeddingModel] = None,
    ):
        super().__init__(embedding_model)
        import faiss
        
        self.dimension = dimension
        self.persist_path = persist_path
        self.faiss = faiss
        
        # Chunk metadata storage (FAISS only stores vectors)
        self._chunks: dict[str, DocumentChunk] = {}
        self._id_to_index: dict[str, int] = {}    # chunk_id -> faiss index
        self._index_to_id: dict[int, str] = {}    # faiss index -> chunk_id
        self._next_index = 0
        
        # Initialize FAISS index
        if persist_path and Path(persist_path).exists():
            self._load(persist_path)
        else:
            self.index = self._create_index(index_type, dimension)
        
        logger.info(
            "FAISS store initialized",
            index_type=index_type,
            dimension=dimension,
            count=self.index.ntotal,
        )
    
    def _create_index(self, index_type: str, dimension: int):
        """Create appropriate FAISS index."""
        if index_type == "flat":
            # Exact search - most accurate, slower for large datasets
            index = self.faiss.IndexFlatIP(dimension)  # Inner product (cosine with normalized vectors)
        elif index_type == "ivf":
            # Approximate search - faster, slight accuracy tradeoff
            nlist = 100  # Number of clusters
            quantizer = self.faiss.IndexFlatIP(dimension)
            index = self.faiss.IndexIVFFlat(
                quantizer, dimension, nlist, self.faiss.METRIC_INNER_PRODUCT
            )
        elif index_type == "hnsw":
            # HNSW - best balance of speed and accuracy
            index = self.faiss.IndexHNSWFlat(dimension, 32)
            index.hnsw.efConstruction = 200
            index.hnsw.efSearch = 64
        else:
            raise ValueError(f"Unknown FAISS index type: {index_type}")
        
        return index
    
    def add_chunks(self, chunks: list[DocumentChunk]) -> list[str]:
        if not chunks:
            return []
        
        embeddings = self._embed_chunks(chunks)
        vectors = np.array(embeddings, dtype=np.float32)
        
        # Normalize for cosine similarity
        self.faiss.normalize_L2(vectors)
        
        # Train IVF index if needed
        if hasattr(self.index, 'is_trained') and not self.index.is_trained:
            logger.info("Training FAISS IVF index...")
            self.index.train(vectors)
        
        # Add vectors
        self.index.add(vectors)
        
        # Store chunk metadata
        ids = []
        for i, chunk in enumerate(chunks):
            faiss_idx = self._next_index + i
            self._chunks[chunk.chunk_id] = chunk
            self._id_to_index[chunk.chunk_id] = faiss_idx
            self._index_to_id[faiss_idx] = chunk.chunk_id
            ids.append(chunk.chunk_id)
        
        self._next_index += len(chunks)
        
        # Auto-save if persist_path is set
        if self.persist_path:
            self._save(self.persist_path)
        
        logger.info("Chunks added to FAISS", count=len(chunks))
        return ids
    
    def search(self, query: SearchQuery) -> list[SearchResult]:
        query_embedding = self._embed_query(query.text)
        query_vector = np.array([query_embedding], dtype=np.float32)
        self.faiss.normalize_L2(query_vector)
        
        # Search
        k = min(query.top_k, self.index.ntotal)
        if k == 0:
            return []
        
        scores, indices = self.index.search(query_vector, k)
        
        results = []
        for rank, (score, faiss_idx) in enumerate(zip(scores[0], indices[0])):
            if faiss_idx == -1:    # FAISS returns -1 for missing
                continue
            
            chunk_id = self._index_to_id.get(faiss_idx)
            if not chunk_id:
                continue
            
            chunk = self._chunks.get(chunk_id)
            if not chunk:
                continue
            
            # Inner product score with normalized vectors = cosine similarity
            similarity = float(score)
            
            if similarity < query.min_score:
                continue
            
            results.append(SearchResult(
                chunk_id=chunk_id,
                doc_id=chunk.doc_id,
                content=chunk.content,
                score=similarity,
                metadata=chunk.metadata,
                rank=rank,
            ))
        
        return results
    
    def delete_document(self, doc_id: str) -> int:
        """Mark document chunks as deleted (FAISS doesn't support true delete)."""
        deleted = 0
        for chunk_id, chunk in list(self._chunks.items()):
            if chunk.doc_id == doc_id:
                del self._chunks[chunk_id]
                idx = self._id_to_index.pop(chunk_id, None)
                if idx is not None:
                    del self._index_to_id[idx]
                deleted += 1
        
        logger.info("Document removed from metadata", doc_id=doc_id, count=deleted)
        return deleted
    
    def get_chunk(self, chunk_id: str) -> Optional[SearchResult]:
        chunk = self._chunks.get(chunk_id)
        if not chunk:
            return None
        return SearchResult(
            chunk_id=chunk_id,
            doc_id=chunk.doc_id,
            content=chunk.content,
            score=1.0,
            metadata=chunk.metadata,
        )
    
    def count(self) -> int:
        return len(self._chunks)
    
    def clear(self) -> None:
        self.index.reset()
        self._chunks.clear()
        self._id_to_index.clear()
        self._index_to_id.clear()
        self._next_index = 0
    
    def _save(self, path: str) -> None:
        """Persist FAISS index and metadata to disk."""
        base_path = Path(path)
        base_path.mkdir(parents=True, exist_ok=True)
        
        self.faiss.write_index(self.index, str(base_path / "index.faiss"))
        
        metadata = {
            "chunks": {k: v.to_dict() for k, v in self._chunks.items()},
            "id_to_index": self._id_to_index,
            "index_to_id": self._index_to_id,
            "next_index": self._next_index,
        }
        
        with open(base_path / "metadata.pkl", "wb") as f:
            pickle.dump(metadata, f)
    
    def _load(self, path: str) -> None:
        """Load FAISS index and metadata from disk."""
        base_path = Path(path)
        self.index = self.faiss.read_index(str(base_path / "index.faiss"))
        
        with open(base_path / "metadata.pkl", "rb") as f:
            metadata = pickle.load(f)
        
        self._id_to_index = metadata["id_to_index"]
        self._index_to_id = metadata["index_to_id"]
        self._next_index = metadata["next_index"]
        logger.info("FAISS store loaded from disk", path=path)


class VectorStoreFactory:
    """Factory for creating vector stores."""
    
    @staticmethod
    def create(
        store_type: VectorStoreType = VectorStoreType.CHROMA,
        embedding_model: Optional[BaseEmbeddingModel] = None,
        **kwargs,
    ) -> BaseVectorStore:
        
        if store_type == VectorStoreType.CHROMA:
            return ChromaVectorStore(
                embedding_model=embedding_model,
                **kwargs,
            )
        elif store_type == VectorStoreType.FAISS:
            return FAISSVectorStore(
                embedding_model=embedding_model,
                **kwargs,
            )
        else:
            raise ValueError(f"Unsupported vector store: {store_type}")
    
    @staticmethod
    def create_default(
        embedding_model: Optional[BaseEmbeddingModel] = None,
    ) -> BaseVectorStore:
        return VectorStoreFactory.create(
            store_type=settings.vector_store_type,
            embedding_model=embedding_model,
        )